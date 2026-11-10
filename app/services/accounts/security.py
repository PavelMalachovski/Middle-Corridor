"""Примитивы входа: нормализация e-mail, хеши кодов и токенов."""

import hashlib
import hmac
import secrets


def normalize_email(raw: str) -> str:
    email = raw.strip().lower()
    if "@" not in email:
        raise ValueError("invalid e-mail")
    return email


def hash_code(secret: str, email: str, code: str) -> str:
    """HMAC-SHA256 по `email:code` с секретом AUTH_SECRET."""
    return hmac.new(secret.encode(), f"{email}:{code}".encode(), hashlib.sha256).hexdigest()


def new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def email_fingerprint(email: str) -> str:
    """Короткий отпечаток адреса для логов и аудита (сам адрес туда не пишем)."""
    return hashlib.sha256(email.encode()).hexdigest()[:12]
