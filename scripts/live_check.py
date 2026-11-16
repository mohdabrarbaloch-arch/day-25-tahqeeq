"""Live end-to-end check against a running server. Not part of the test suite."""

from __future__ import annotations

import json
import sys

import httpx

BASE = "http://127.0.0.1:8025"

GOOD = (
    "ISLAMABAD — The Ministry of Finance said on Monday that inflation eased to "
    "4.2 percent in October, down from 5.1 percent the previous month, according "
    "to data released by the Pakistan Bureau of Statistics. A senior official at "
    "the bureau, speaking on condition of anonymity because the figures were not "
    'yet public, said the decline was driven by lower food prices. "Food '
    'inflation has come down sharply," the official said. The bureau is '
    "scheduled to publish the full breakdown on 25 November."
)

BAD = (
    "SHOCKING!!! You won't BELIEVE what they are hiding about the economy!!! "
    "Sources say the government is about to DESTROY the rupee and wipe out "
    "everyone's savings. The mainstream media is SILENT about this. Share this "
    "before it gets deleted!!!"
)

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        failures.append(name)


def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=30.0)

    print("\n[1] health")
    r = c.get("/api/health")
    check("health 200", r.status_code == 200, str(r.status_code))
    body = r.json()
    check("db ok", body.get("database") == "ok", json.dumps(body))
    print(f"        {json.dumps(body)}")

    print("\n[2] security headers")
    for header in (
        "x-content-type-options",
        "x-frame-options",
        "referrer-policy",
        "content-security-policy",
    ):
        check(f"header {header}", header in {k.lower() for k in r.headers})

    print("\n[3] docs disabled in production")
    r = c.get("/docs")
    check("/docs is 404", r.status_code == 404, str(r.status_code))

    print("\n[4] register")
    r = c.post(
        "/api/auth/register",
        json={"email": "live@tahqeeq.pk", "password": "correct-horse-battery"},
    )
    check("register 201", r.status_code == 201, r.text[:200])
    token = r.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    print("\n[5] duplicate register is 409")
    r = c.post(
        "/api/auth/register",
        json={"email": "live@tahqeeq.pk", "password": "correct-horse-battery"},
    )
    check("duplicate 409", r.status_code == 409, str(r.status_code))

    print("\n[6] login")
    r = c.post(
        "/api/auth/login",
        json={"email": "live@tahqeeq.pk", "password": "correct-horse-battery"},
    )
    check("login 200", r.status_code == 200, r.text[:200])

    print("\n[7] wrong password is 401")
    r = c.post(
        "/api/auth/login",
        json={"email": "live@tahqeeq.pk", "password": "wrong-password-here"},
    )
    check("bad password 401", r.status_code == 401, str(r.status_code))

    print("\n[8] preview needs no auth")
    r = c.post("/api/analyses/preview", json={"text": GOOD})
    check("preview 200", r.status_code == 200, r.text[:300])
    good_score = r.json()["score"]
    print(f"        good article score = {good_score}")

    r = c.post("/api/analyses/preview", json={"text": BAD})
    bad_score = r.json()["score"]
    print(f"        hype article score = {bad_score}")
    check("good > bad by 25+", good_score - bad_score >= 25, f"{good_score} vs {bad_score}")

    print("\n[9] save an analysis")
    r = c.post(
        "/api/analyses",
        json={"text": GOOD, "headline": "Inflation eases to 4.2 percent in October"},
        headers=auth,
    )
    check("create 201", r.status_code == 201, r.text[:300])
    created = r.json()
    aid = created["id"]
    print(f"        id={aid} score={created['score']} band={created['band']}")
    print(f"        confidence={created['confidence']} words={created['word_count']}")
    check("has 11 signals", len(created["result"]["signals"]) == 11)
    check(
        "headline signal applies",
        any(s["id"] == "headline_body" and s["applies"] for s in created["result"]["signals"]),
    )

    print("\n[10] list")
    r = c.get("/api/analyses", headers=auth)
    check("list 200", r.status_code == 200)
    check("list has 1", r.json()["total"] == 1, str(r.json()["total"]))

    print("\n[11] read one back")
    r = c.get(f"/api/analyses/{aid}", headers=auth)
    check("get 200", r.status_code == 200)
    check("score stable", r.json()["score"] == created["score"])

    print("\n[12] validation")
    r = c.post("/api/analyses", json={"text": "too short"}, headers=auth)
    check("short text 422", r.status_code == 422, str(r.status_code))
    print(f"        {r.json().get('detail')}")

    print("\n[13] SSRF guard")
    for url in (
        "http://127.0.0.1:8025/api/health",
        "http://localhost/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
    ):
        r = c.post("/api/analyses/preview-url", json={"url": url})
        check(f"blocked {url}", r.status_code == 422, f"{r.status_code} {r.text[:120]}")

    print("\n[14] ownership returns 404")
    r = c.post(
        "/api/auth/register",
        json={"email": "other@tahqeeq.pk", "password": "another-good-password"},
    )
    other = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = c.get(f"/api/analyses/{aid}", headers=other)
    check("other user 404", r.status_code == 404, str(r.status_code))
    r = c.delete(f"/api/analyses/{aid}", headers=other)
    check("other delete 404", r.status_code == 404, str(r.status_code))

    print("\n[15] unauthenticated is 401")
    r = c.get("/api/analyses")
    check("no token 401", r.status_code == 401, str(r.status_code))

    print("\n[16] delete")
    r = c.delete(f"/api/analyses/{aid}", headers=auth)
    check("delete 204", r.status_code == 204, str(r.status_code))
    r = c.get(f"/api/analyses/{aid}", headers=auth)
    check("gone 404", r.status_code == 404, str(r.status_code))

    print("\n[17] SPA is served")
    r = c.get("/")
    check("index 200", r.status_code == 200)
    check("has app root", 'id="app"' in r.text or "Tahqeeq" in r.text)
    r = c.get("/static/app.js")
    check("app.js 200", r.status_code == 200)
    r = c.get("/static/styles.css")
    check("styles.css 200", r.status_code == 200)

    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL LIVE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
