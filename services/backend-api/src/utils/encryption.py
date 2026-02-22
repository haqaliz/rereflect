"""
Fernet symmetric encryption utilities for BYOK API key storage.

The encryption key is sourced from the LLM_ENCRYPTION_KEY environment variable.
Generate once: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
import os
from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Fernet:
    """Get Fernet instance using LLM_ENCRYPTION_KEY env var."""
    key = os.environ.get("LLM_ENCRYPTION_KEY")
    if not key:
        raise ValueError("LLM_ENCRYPTION_KEY environment variable is not set")
    return Fernet(key.encode())


def encrypt_api_key(plain_key: str) -> str:
    """Encrypt an API key using Fernet symmetric encryption."""
    fernet = _get_fernet()
    return fernet.encrypt(plain_key.encode()).decode()


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt an encrypted API key. Raises InvalidToken if key is corrupted."""
    fernet = _get_fernet()
    return fernet.decrypt(encrypted_key.encode()).decode()


def get_key_hint(plain_key: str) -> str:
    """Return the last 4 characters of a key for display (e.g., '...abc1')."""
    if len(plain_key) >= 4:
        return f"...{plain_key[-4:]}"
    return plain_key
