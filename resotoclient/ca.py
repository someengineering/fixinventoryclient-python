from cryptography.x509.base import Certificate
from cryptography import x509
import warnings
import requests
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import NameOID
from resotoclient.jwt_utils import decode_jwt_from_headers
from jwt.exceptions import InvalidSignatureError
import logging
from logging import Logger
import certifi
import os
from typing import Optional
import tempfile
import time
from datetime import timedelta, datetime
from tempfile import TemporaryDirectory
from threading import Lock, Thread, Condition, Event


def load_cert_from_bytes(cert: bytes) -> Certificate:
    return x509.load_pem_x509_certificate(cert, default_backend())


def load_cert_from_file(cert_path: str) -> Certificate:
    with open(cert_path, "rb") as f:
        return load_cert_from_bytes(f.read())


def cert_fingerprint(cert: Certificate, hash_algorithm: str = "SHA256") -> str:
    return ":".join(
        f"{b:02X}" for b in cert.fingerprint(getattr(hashes, hash_algorithm.upper())())
    )


def get_ca_cert(resotocore_uri: str, psk: Optional[str]) -> Certificate:

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        r = requests.get(f"{resotocore_uri}/ca/cert", verify=False)
        ca_cert = load_cert_from_bytes(r.content)
        if psk:
            jwt = decode_jwt_from_headers(dict(r.headers), psk)
            if jwt is None:
                raise NoJWTError("Failed to decode JWT")
            if jwt["sha256_fingerprint"] != cert_fingerprint(ca_cert):
                raise FingerprintError("Invalid Root CA certificate fingerprint")
        return ca_cert


def cert_to_bytes(cert: Certificate) -> bytes:
    return cert.public_bytes(serialization.Encoding.PEM)


def write_ca_bundle(
    cert: Certificate, cert_path: str, include_certifi: bool = True, rename: bool = True
) -> None:
    tmp_cert_path = f"{cert_path}.tmp" if rename else cert_path
    with open(tmp_cert_path, "wb") as f:
        if include_certifi:
            f.write(certifi.contents().encode())
        f.write("\n".encode())
        f.write(f"# Issuer: {cert.issuer.rfc4514_string()}\n".encode())
        f.write(f"# Subject: {cert.subject.rfc4514_string()}\n".encode())
        label = cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        f.write(f"# Label: {label}\n".encode())
        f.write(f"# Serial: {cert.serial_number}\n".encode())
        md5 = cert_fingerprint(cert, "MD5")
        sha1 = cert_fingerprint(cert, "SHA1")
        sha256 = cert_fingerprint(cert, "SHA256")
        f.write(f"# MD5 Fingerprint: {md5}\n".encode())
        f.write(f"# SHA1 Fingerprint: {sha1}\n".encode())
        f.write(f"# SHA256 Fingerprint: {sha256}\n".encode())
        f.write(cert_to_bytes(cert))
    if rename:
        os.rename(tmp_cert_path, cert_path)


def load_ca_cert(resotocore_uri: str, psk: Optional[str]) -> str:
    logging.debug("Loading CA cert from core")
    _, filename = tempfile.mkstemp()

    ca_cert = get_ca_cert(resotocore_uri=resotocore_uri, psk=psk)
    logging.debug(f"Writing CA cert {filename}")
    write_ca_bundle(ca_cert, filename, include_certifi=True)
    return filename


def load_cert_from_core(
    ca_cert_path: str, resotocore_uri: str, psk: Optional[str], log: Logger
) -> Certificate:
    log.debug("Loading CA certificate from core")
    try:
        ca_cert = get_ca_cert(resotocore_uri=resotocore_uri, psk=psk)
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
    log.debug(f"Writing CA cert {ca_cert_path}")
    write_ca_bundle(ca_cert, ca_cert_path, include_certifi=True)
    return ca_cert


def refresh_cert_on_disk(
    ca_cert_path: str, ca_cert: Certificate, log: Logger, refresh_every_sec: int = 10800
) -> None:
    try:
        last_ca_cert_update = time.time() - os.path.getmtime(ca_cert_path)
        if last_ca_cert_update > refresh_every_sec:
            log.debug("Refreshing cert/key files on disk")
            write_ca_bundle(ca_cert, ca_cert_path, include_certifi=True)
    except FileNotFoundError:
        pass


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
        self.__custom_ca_cert_path = custom_ca_cert_path
        self.__ca_cert = None
        self.__tempdir = TemporaryDirectory(prefix="resoto-cert-")
        self.__ca_cert_path = f"{self.__tempdir.name}/ca.crt"
        self.__renew_before = renew_before
        self.__watcher = Thread(
            target=self.__certificates_watcher, name="certificates_watcher"
        )
        self.__load_lock = Lock()
        self.__loaded = Event()
        self.__exit = Condition()

        self.log = logging.getLogger("resotoclient")

    def start(self) -> None:
        self.load()
        if not self.__watcher.is_alive():
            self.__watcher.start()

    def shutdown(self) -> None:
        with self.__exit:
            self.__exit.notify()

    def load(self) -> None:
        with self.__load_lock:
            if self.__custom_ca_cert_path is not None:
                self.log.debug(
                    f"Loading CA certificate from {self.__custom_ca_cert_path}"
                )
                self.__ca_cert = load_cert_from_file(self.__custom_ca_cert_path)
            else:
                self.__ca_cert = load_cert_from_core(
                    self.__ca_cert_path, self.resotocore_url, self.psk, self.log
                )
            self.__loaded.set()

    def reload(self) -> None:
        self.__loaded.clear()
        self.load()

    def ca_cert_path(self) -> str:
        if not os.path.isfile(self.__ca_cert_path):
            self.load()
        return self.__ca_cert_path

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
                        self.reload()
                    self.__refresh_files_on_disk()
                if self.__exit.wait(60):
                    break

    def __refresh_files_on_disk(self) -> None:
        if not self.__loaded.is_set():
            return
        if self.__ca_cert is None:
            return
        refresh_cert_on_disk(
            ca_cert_path=self.__ca_cert_path, ca_cert=self.__ca_cert, log=self.log
        )
