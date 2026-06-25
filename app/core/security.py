import base64
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

AES_KEY = settings.JWT_SECRET_KEY.encode("utf-8")[:32]
ALGORITHM = "HS256"


def _get_cipher(iv: bytes) -> Cipher:
    return Cipher(algorithms.AES(AES_KEY), modes.CBC(iv), backend=default_backend())


def _pad(data: bytes) -> bytes:
    padder = sym_padding.PKCS7(128).padder()
    return padder.update(data) + padder.finalize()


def _unpad(padded: bytes) -> bytes:
    unpadder = sym_padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def encrypt_payload(payload: str) -> str:
    iv = os.urandom(16)
    cipher = _get_cipher(iv)
    encryptor = cipher.encryptor()
    padded = _pad(payload.encode("utf-8"))
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.urlsafe_b64encode(iv + ciphertext).decode("utf-8")


def decrypt_payload(token: str) -> str:
    raw = base64.urlsafe_b64decode(token.encode("utf-8"))
    iv, ciphertext = raw[:16], raw[16:]
    cipher = _get_cipher(iv)
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    return _unpad(padded).decode("utf-8")


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    signed = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)
    return encrypt_payload(signed)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        signed = decrypt_payload(token)
        return jwt.decode(signed, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])
    except Exception as exc:
        raise JWTError(str(exc)) from exc


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_password_reset_token() -> str:
    return secrets.token_urlsafe(32)


def refresh_token_expires_at() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)


def password_reset_expires_at() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES)
