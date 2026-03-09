"""
Fernet symmetric encryption for user Anthropic API keys stored at rest.
Keys are encrypted before writing to the DB and decrypted on read.
"""

from cryptography.fernet import Fernet, InvalidToken

from backend.config import settings


def _fernet() -> Fernet:
    if not settings.encryption_key:
        raise RuntimeError("ENCRYPTION_KEY is not set in environment")
    return Fernet(settings.encryption_key.encode())


def encrypt_api_key(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode())


def decrypt_api_key(ciphertext: bytes) -> str:
    try:
        return _fernet().decrypt(ciphertext).decode()
    except InvalidToken as e:
        raise ValueError("Failed to decrypt API key — invalid or corrupt ciphertext") from e
