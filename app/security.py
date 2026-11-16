"""Password hashing and JWT handling.

bcrypt for passwords, HS256 for tokens. Both are boring on purpose — the
interesting security work in this app is the SSRF guard and the owner-scoped
queries, not inventing a new auth scheme.

**Why bcrypt directly and not passlib:** passlib 1.7.4 has been unmaintained
since 2020 and reads `bcrypt.__about__.__version__`, which bcrypt 4.x removed.
The result is a "(trapped) error reading bcrypt version" traceback on every
hash. Rather than pin an old bcrypt to satisfy a dead library, this calls
bcrypt's own API, which is two functions and has no such problem.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from app.config import settings

ALGORITHM = "HS256"

# bcrypt silently truncates at 72 bytes. Truncating silently is a security
# bug — two different long passwords would hash the same — so this rejects
# instead, and the schema's 128-char limit keeps normal use well inside it.
BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_BYTES:
        raise ValueError(
            f"Password is too long: {len(encoded)} bytes, bcrypt's limit is {BCRYPT_MAX_BYTES}."
        )
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    return bcrypt.hashpw(encoded, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        encoded = plain.encode("utf-8")
        if len(encoded) > BCRYPT_MAX_BYTES:
            return False
        return bcrypt.checkpw(encoded, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # A malformed hash must read as "wrong password", never as a crash.
        return False


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    minutes = (
        expires_minutes if expires_minutes is not None else settings.access_token_expire_minutes
    )
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str | None:
    """Return the subject, or None if the token is invalid or expired."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None
    subject = payload.get("sub")
    return subject if isinstance(subject, str) else None
