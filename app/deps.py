"""Shared FastAPI dependencies: current user, rate limiting."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import User, get_db
from app.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the bearer token to a user, or 401.

    The message is deliberately identical for "no token", "bad token" and
    "user gone" — the API should not help anyone enumerate accounts.
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or not credentials.credentials:
        raise unauthorized

    subject = decode_access_token(credentials.credentials)
    if subject is None:
        raise unauthorized

    try:
        user_id = int(subject)
    except (TypeError, ValueError):
        raise unauthorized from None

    user = db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


class RateLimiter:
    """A sliding-window limiter, in process.

    Honest about its limit: behind N workers the effective rate is N × the
    configured value. Redis is the fix and it is listed as open work rather
    than pretended away.
    """

    def __init__(self, requests: int, window_seconds: int) -> None:
        self.requests = requests
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        now = time.monotonic()
        cutoff = now - self.window
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.requests:
                retry_after = int(self.window - (now - bucket[0])) + 1
                return False, max(1, retry_after)
            bucket.append(now)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


_limiter = RateLimiter(settings.rate_limit_requests, settings.rate_limit_window_seconds)


def rate_limit(request: Request) -> None:
    """Dependency that enforces the per-IP limit."""
    client = request.client.host if request.client else "unknown"
    allowed, retry_after = _limiter.check(client)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Slow down and try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )


def get_rate_limiter() -> RateLimiter:
    """Exposed so tests can reset the window between cases."""
    return _limiter


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower()))
