"""End-to-end smoke test against a real TestClient. Not part of the suite."""

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
os.environ["SECRET_KEY"] = "test-key-for-smoke-run-only-not-production"

from fastapi.testclient import TestClient

from app.main import app

GOOD = """ISLAMABAD — The Ministry of Finance said on Monday that inflation eased to 4.2 percent in October, down from 5.1 percent the previous month, according to data released by the Pakistan Bureau of Statistics.

"The decline reflects lower food prices and a stable rupee," said a spokesperson for the ministry in a statement. The bureau reported that food inflation fell 1.8 percentage points, while core inflation, which excludes food and energy, was roughly unchanged at 6.4 percent.

Economists cautioned that the improvement may be temporary. "One month does not make a trend," said Dr. Ayesha Khan, an economist at the Lahore School of Economics, in an interview with Reuters. She noted that the figures could be revised next quarter.

The State Bank of Pakistan is expected to review its policy rate at its next meeting on 2 December. Analysts surveyed by Bloomberg estimated a 50 basis point cut is likely, though the central bank declined to comment."""

with TestClient(app) as client:
    print("health:", client.get("/api/health").status_code, client.get("/api/health").json())

    r = client.post("/api/auth/register", json={"email": "a@b.com", "password": "correct-horse-9"})
    print("register:", r.status_code)
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    print("me:", client.get("/api/auth/me", headers=headers).status_code)

    r = client.post(
        "/api/analyses",
        json={"text": GOOD, "headline": "Inflation eases to 4.2 percent in October"},
        headers=headers,
    )
    print("create:", r.status_code)
    body = r.json()
    print(
        "  score:", body["score"], "band:", body["band"], "signals:", len(body["result"]["signals"])
    )
    aid = body["id"]

    print("list:", client.get("/api/analyses", headers=headers).json()["total"])
    print("get:", client.get(f"/api/analyses/{aid}", headers=headers).status_code)
    print("preview:", client.post("/api/analyses/preview", json={"text": GOOD}).status_code)
    print("unauth get:", client.get(f"/api/analyses/{aid}").status_code)
    print("delete:", client.delete(f"/api/analyses/{aid}", headers=headers).status_code)
    print("get after delete:", client.get(f"/api/analyses/{aid}", headers=headers).status_code)

    # security headers
    h = client.get("/api/health").headers
    print("nosniff:", h.get("x-content-type-options"), "| frame:", h.get("x-frame-options"))
