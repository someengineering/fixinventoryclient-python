from cryptography.x509.base import Certificate
from cryptography import x509
import warnings
import aiohttp
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import NameOID
from resotoclient.jwt_utils import decode_jwt_from_headers
from jwt.exceptions import InvalidSignatureError
import logging
from logging import Logger
from typing import Optional, Mapping, Tuple
import asyncio
from datetime import timedelta, datetime
from threading import Lock, Thread, Condition, Event
from ssl import SSLContext, create_default_context, Purpose
import certifi
from io import StringIO

def load_cert_from_bytes(cert: bytes) -> Certificate:
    return x509.load_pem_x509_certificate(cert, default_backend())


def load_cert_from_file(cert_path: str) -> Certificate:
    with open(cert_path, "rb") as f:
        return load_cert_from_bytes(f.read())


def cert_fingerprint(cert: Certificate, hash_algorithm: str = "SHA256") -> str:
    return ":".join(
        f"{b:02X}" for b in cert.fingerprint(getattr(hashes, hash_algorithm.upper())())
    )


# yep, this is an expensive call to make. But we only call it when the certificate
# needs to be refreshed, which is not happening often, so it is fine here.
async def get_ca_cert(resotocore_uri: str, psk: Optional[str]) -> Certificate:
    async def do_request() -> Tuple[bytes, Mapping[str, str]]:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{resotocore_uri}/ca/cert", ssl=False) as response:
                return await response.read(), response.headers


    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        content, headers = await do_request()
        ca_cert = load_cert_from_bytes(content)
        if psk:
            jwt = decode_jwt_from_headers(dict(headers), psk)
            if jwt is None:
                raise NoJWTError("Failed to decode JWT")
            if jwt["sha256_fingerprint"] != cert_fingerprint(ca_cert):
                raise FingerprintError("Invalid Root CA certificate fingerprint")
        return ca_cert


def cert_to_bytes(cert: Certificate) -> bytes:
    return cert.public_bytes(serialization.Encoding.PEM)


def ca_bundle(
    cert: Certificate, include_certifi: bool = True
) -> str:
    f = StringIO()
    if include_certifi:
        f.write(certifi.contents())
    f.write("\n")
    f.write(f"# Issuer: {cert.issuer.rfc4514_string()}\n")
    f.write(f"# Subject: {cert.subject.rfc4514_string()}\n")
    label = cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    f.write(f"# Label: {label}\n")
    f.write(f"# Serial: {cert.serial_number}\n")
    md5 = cert_fingerprint(cert, "MD5")
    sha1 = cert_fingerprint(cert, "SHA1")
    sha256 = cert_fingerprint(cert, "SHA256")
    f.write(f"# MD5 Fingerprint: {md5}\n")
    f.write(f"# SHA1 Fingerprint: {sha1}\n")
    f.write(f"# SHA256 Fingerprint: {sha256}\n")
    f.write(cert_to_bytes(cert).decode("utf-8"))
    return f.getvalue()

async def load_cert_from_core(
    resotocore_uri: str, psk: Optional[str], log: Logger
) -> Certificate:
    log.debug("Loading CA certificate from core")
    try:
        ca_cert = await get_ca_cert(resotocore_uri=resotocore_uri, psk=psk)
    except FingerprintError as e:
        log.fatal(f"{e}, MITM attack?")
        raise
    except InvalidSignatureError as e:
        log.fatal(f"{e}, wrong PSK?")
        raise
    except NoJWTError as e:
        log.fatal(f"{e}, resotocore started without PSK?")
        raise
    except Exception as e:
        log.fatal(f"{e}")
        raise
    return ca_cert


class FingerprintError(Exception):
    pass


class NoJWTError(Exception):
    pass


class CertificatesHolder:
    def __init__(
        self,
        resotocore_url: str,
        psk: Optional[str],
        custom_ca_cert_path: Optional[str],
        renew_before: timedelta,
    ) -> None:
        self.resotocore_url = resotocore_url
        self.psk = psk
        self.__ca_cert = None
        self.__custom_ca_cert_path = custom_ca_cert_path
        self.__ssl_context = None
        self.__renew_before = renew_before
        self.__watcher = Thread(
            target=self.__certificates_watcher, name="certificates_watcher", daemon=True
        )
        self.__load_lock = Lock()
        self.__loaded = Event()
        self.__exit = Condition()

        self.log = logging.getLogger("resotoclient")

    async def start(self) -> None:
        await self.load()
        if not self.__watcher.is_alive():
            self.__watcher.start()

    def shutdown(self) -> None:
        with self.__exit:
            self.__exit.notify()

    async def load(self) -> None:
        with self.__load_lock:
            if self.__custom_ca_cert_path is not None:
                self.log.debug(
                    f"Loading CA certificate from {self.__custom_ca_cert_path}"
                )
                self.__ca_cert = load_cert_from_file(self.__custom_ca_cert_path)
            else:
                self.__ca_cert = await load_cert_from_core(
                    self.resotocore_url, self.psk, self.log
                )
            ctx = create_default_context(purpose=Purpose.SERVER_AUTH)
            ctx.load_verify_locations(cadata=ca_bundle(self.__ca_cert))
            self.__ssl_context = ctx
            self.__loaded.set()

    async def reload(self) -> None:
        self.__loaded.clear()
        await self.load()

    async def ssl_context(self) -> SSLContext:
        if not self.__ssl_context:
            await self.load()
        return self.__ssl_context # type: ignore


    def __certificates_watcher(self) -> None:
        while True:
            with self.__exit:
                if self.__loaded.is_set():
                    cert = self.__ca_cert
                    if (
                        isinstance(cert, Certificate)
                        and cert.not_valid_after
                        < datetime.utcnow() - self.__renew_before
                    ):
                        asyncio.run(self.reload())
                if self.__exit.wait(60):
                    break