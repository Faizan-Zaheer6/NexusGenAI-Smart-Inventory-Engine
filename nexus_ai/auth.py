import os
from datetime import datetime, timedelta
import base64
from typing import Any, Dict

from bcrypt import hashpw, gensalt, checkpw
from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from jose import JWTError, jwt

# ---------------------------------------------------------------------------
# Configuration (environment variables)
# ---------------------------------------------------------------------------
# Secret key used for signing JWTs (HS256). Must be at least 32 characters for security.
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "default_jwt_secret_change_me_please!")
# AES-256 encryption key derived from the same secret (must be 32 bytes).
AES_KEY = JWT_SECRET_KEY.encode("utf-8")[:32]
# Token expiry (default 1 hour)
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

def _get_cipher(iv: bytes) -> Cipher:
    """Create a Cipher object for AES-256-CBC encryption/decryption.
    The IV must be 16 bytes.
    """
    return Cipher(algorithms.AES(AES_KEY), modes.CBC(iv), backend=default_backend())

def _pad(data: bytes) -> bytes:
    padder = sym_padding.PKCS7(128).padder()
    return padder.update(data) + padder.finalize()

def _unpad(padded: bytes) -> bytes:
    unpadder = sym_padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()

def encrypt_payload(payload: str) -> str:
    """Encrypt a UTF‑8 string with AES‑256‑CBC and return a base64 string.
    The first 16 bytes of the ciphertext are the random IV.
    """
    iv = os.urandom(16)
    cipher = _get_cipher(iv)
    encryptor = cipher.encryptor()
    padded = _pad(payload.encode("utf-8"))
    ct = encryptor.update(padded) + encryptor.finalize()
    return base64.urlsafe_b64encode(iv + ct).decode("utf-8")

def decrypt_payload(token: str) -> str:
    """Decrypt a base64‑encoded AES‑256‑CBC token and return the original string."""
    raw = base64.urlsafe_b64decode(token.encode("utf-8"))
    iv, ct = raw[:16], raw[16:]
    cipher = _get_cipher(iv)
    decryptor = cipher.decryptor()
    padded = decryptor.update(ct) + decryptor.finalize()
    return _unpad(padded).decode("utf-8")

def create_access_token(data: Dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Create a signed JWT, then encrypt the whole token.
    The JWT payload is the provided ``data`` dict plus the standard ``exp`` claim.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    signed = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm="HS256")
    encrypted = encrypt_payload(signed)
    return encrypted

def decode_access_token(token: str) -> Dict[str, Any]:
    """Decrypt the token and verify the JWT signature.
    Returns the payload dict if valid, otherwise raises ``JWTError``.
    """
    try:
        signed = decrypt_payload(token)
        payload = jwt.decode(signed, JWT_SECRET_KEY, algorithms=["HS256"])
        return payload
    except Exception as e:
        raise JWTError(str(e))

def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt (12 rounds)."""
    return hashpw(password.encode("utf-8"), gensalt()).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a bcrypt hash."""
    return checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
