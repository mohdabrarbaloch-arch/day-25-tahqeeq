"""Shared fixtures. Every test runs against a throwaway SQLite file."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest

# These must be set before app.config is imported anywhere.
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mktemp(suffix='.db')}")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-use-only")
os.environ.setdefault("BCRYPT_ROUNDS", "4")  # fast hashing in tests
os.environ.setdefault("RATE_LIMIT_REQUESTS", "10000")  # don't trip the limiter


@pytest.fixture(scope="session")
def app_module():
    from app.main import app

    return app


@pytest.fixture()
def client(app_module) -> Iterator:
    from fastapi.testclient import TestClient

    with TestClient(app_module) as test_client:
        yield test_client


@pytest.fixture()
def auth_headers(client) -> dict[str, str]:
    """A registered user's bearer token."""
    import uuid

    email = f"user-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "a-good-password-9"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


GOOD_ARTICLE = """ISLAMABAD — The Ministry of Finance said on Monday that inflation eased to 4.2 percent in October, down from 5.1 percent the previous month, according to data released by the Pakistan Bureau of Statistics.

"The decline reflects lower food prices and a stable rupee," said a spokesperson for the ministry in a statement. The bureau reported that food inflation fell 1.8 percentage points, while core inflation, which excludes food and energy, was roughly unchanged at 6.4 percent.

Economists cautioned that the improvement may be temporary. "One month does not make a trend," said Dr. Ayesha Khan, an economist at the Lahore School of Economics, in an interview with Reuters. She noted that the figures could be revised next quarter.

The State Bank of Pakistan is expected to review its policy rate at its next meeting on 2 December. Analysts surveyed by Bloomberg estimated a 50 basis point cut is likely, though the central bank declined to comment."""

BAD_ARTICLE = """SHOCKING!!! You won't BELIEVE what they are hiding about the economy!!!

Sources say the government is about to DESTROY the rupee completely. Insiders claim the real truth is being suppressed by the mainstream media, and thousands of people are already panicking. This is a total DISASTER and nobody is talking about it!

They don't want you to know that the deep state has a hidden agenda. Everyone knows the elites are controlling everything. Do your own research! The truth will blow your mind!!!

Share this before it gets deleted! Forward this to everyone you know. Act now before they silence us!"""


@pytest.fixture()
def good_article() -> str:
    return GOOD_ARTICLE


@pytest.fixture()
def bad_article() -> str:
    return BAD_ARTICLE
