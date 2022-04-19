from cryptography.x509.base import Certificate
from cryptography import x509
import warnings
import requests
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import NameOID
from resotoclient.jwt_utils import decode_jwt_from_headers
import logging
import certifi
import os
from typing import Optional
import tempfile


def load_cert_from_bytes(cert: bytes) -> Certificate:
    return x509.load_pem_x509_certificate(cert, default_backend())


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
            # noinspection PyTypeChecker
            jwt = decode_jwt_from_headers(dict(r.headers), psk)
            if jwt is None:
                raise ValueError(
                    "Failed to decode JWT - was resotocore started without PSK?"
                )
            if jwt["sha256_fingerprint"] != cert_fingerprint(ca_cert):
                raise ValueError("Invalid Root CA certificate fingerprint")
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
