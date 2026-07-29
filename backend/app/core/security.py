"""Password hashing + JWT issuance/verification.

Uses `bcrypt` directly rather than via `passlib.CryptContext`: passlib 1.7.x's
bcrypt backend self-test is incompatible with bcrypt>=4.1 (which dropped the
`__about__` attribute passlib probes for version detection, and enforces the
72-byte input limit passlib's own bug-detection routine trips over) - a
known, currently-unresolved upstream incompatibility. Calling bcrypt
directly sidesteps it entirely with no functional loss.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()

# bcrypt silently truncates/errors past 72 bytes; hash the SHA-256 digest of
# the password instead of the raw password so length is never a concern
# while all of the entered password material still affects the hash.
import hashlib as _hashlib


def _prehash(password: str) -> bytes:
    return _hashlib.sha256(password.encode("utf-8")).digest()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(_prehash(plain), hashed.encode("utf-8"))


def create_access_token(subject: str, role: str, expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    payload: dict[str, Any] = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


# ── API keys (service-to-service auth, separate from human login) ──────────
# Keys are high-entropy random tokens, not user-chosen passwords, so a fast
# salted hash (SHA-256) is standard practice here - unlike passwords, there's
# no offline-guessing risk to defend against with a slow hash like bcrypt.
import secrets as _secrets


def generate_api_key() -> tuple[str, str, str]:
    """Returns (raw_key_to_show_once, prefix_for_display, hash_to_store)."""
    raw = "rk_" + _secrets.token_urlsafe(32)
    prefix = raw[:12]
    return raw, prefix, hash_api_key(raw)


def hash_api_key(raw: str) -> str:
    return _hashlib.sha256(raw.encode("utf-8")).hexdigest()
