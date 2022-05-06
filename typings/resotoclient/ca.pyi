"""
This type stub file was generated by pyright.
"""

from cryptography.x509.base import Certificate
from logging import Logger
from typing import Optional
from datetime import timedelta

def load_cert_from_bytes(cert: bytes) -> Certificate: ...
def load_cert_from_file(cert_path: str) -> Certificate: ...
def cert_fingerprint(cert: Certificate, hash_algorithm: str = ...) -> str: ...
def get_ca_cert(resotocore_uri: str, psk: Optional[str]) -> Certificate: ...
def cert_to_bytes(cert: Certificate) -> bytes: ...
def write_ca_bundle(
    cert: Certificate, cert_path: str, include_certifi: bool = ..., rename: bool = ...
) -> None: ...
def load_ca_cert(resotocore_uri: str, psk: Optional[str]) -> str: ...
def load_cert_from_core(
    ca_cert_path: str, resotocore_uri: str, psk: Optional[str], log: Logger
) -> Certificate: ...
def refresh_cert_on_disk(
    ca_cert_path: str, ca_cert: Certificate, log: Logger, refresh_every_sec: int = ...
) -> None: ...

class FingerprintError(Exception): ...
class NoJWTError(Exception): ...

class CertificatesHolder:
    def __init__(
        self,
        resotocore_url: str,
        psk: Optional[str],
        custom_ca_cert_path: Optional[str],
        renew_before: timedelta,
    ) -> None: ...
    def start(self) -> None: ...
    def shutdown(self) -> None: ...
    def load(self) -> None: ...
    def reload(self) -> None: ...
    def ca_cert_path(self) -> str: ...
