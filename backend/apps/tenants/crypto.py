"""Bot token encryption at rest (CLAUDE.md §5) — never store a plaintext token."""

from cryptography.fernet import Fernet
from django.conf import settings


def _fernet() -> Fernet:
    key = settings.FERNET_KEY
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(raw_token: str) -> str:
    return _fernet().encrypt(raw_token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    return _fernet().decrypt(encrypted_token.encode()).decode()
