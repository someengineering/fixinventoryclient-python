from typing import Dict, Any, Optional, Tuple
import os
import jwt
import base64
import hashlib
import time


def key_from_psk(psk: str, salt: Optional[bytes] = None) -> Tuple[bytes, bytes]:
    """Derive a 256 bit key from a passphrase/pre-shared-key.
    A salt can be optionally provided. If not one will be generated.
    Returns both the key and the salt.
    """
    if salt is None:
        salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", psk.encode(), salt, 100000)
    return key, salt


def encode_jwt(
    payload: Dict[str, Any],
    psk: str,
    headers: Optional[Dict[str, str]] = None,
    expire_in: int = 300,
) -> str:
    """Encodes a payload into a JWT and signs using a key derived from a pre-shared-key.
    Stores the key's salt in the JWT headers.
    """
    payload = dict(payload)
    if headers is None:
        headers = {}
    if expire_in > 0 and "exp" not in payload:
        payload.update({"exp": int(time.time()) + expire_in})
    key, salt = key_from_psk(psk)
    salt_encoded = base64.standard_b64encode(salt).decode("utf-8")
    headers.update({"salt": salt_encoded})
    return jwt.encode(payload, key, algorithm="HS256", headers=headers)


def encode_jwt_to_headers(
    http_headers: Dict[str, str],
    payload: Dict[str, Any],
    psk: str,
    scheme: str = "Bearer",
    headers: Optional[Dict[str, str]] = None,
    expire_in: int = 300,
) -> Dict[str, str]:
    """Takes a payload and psk turns them into a JWT and adds that to a http headers
    dictionary. Also returns that dict.
    """
    http_headers.update(
        {"Authorization": f"{scheme} {encode_jwt(payload, psk, headers, expire_in)}"}
    )
    return http_headers
