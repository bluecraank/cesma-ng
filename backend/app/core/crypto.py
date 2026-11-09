"""Symmetric encryption for secrets stored in the database (device passwords, keys, backups)."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class SecretBox:
    """Encrypts and decrypts strings with a key derived from the application secret."""

    def __init__(self, secret: str) -> None:
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("Secret could not be decrypted (wrong CESMA_SECRET_KEY?)") from exc
