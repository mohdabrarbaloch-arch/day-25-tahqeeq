"""Tests for the API: auth, ownership, validation, and the SSRF guard."""

from __future__ import annotations

import pytest

from app.engine.fetcher import FetchError, assert_safe_url, html_to_text


class TestHealth:
    def test_health_ok(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["database"] == "ok"

    def test_security_headers_present(self, client):
        headers = client.get("/api/health").headers
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["x-frame-options"] == "DENY"
        assert "content-security-policy" in headers


class TestAuth:
    def test_register_returns_token(self, client):
        response = client.post(
            "/api/auth/register",
            json={"email": "new-user@example.com", "password": "a-good-password-9"},
        )
        assert response.status_code == 201
        assert "access_token" in response.json()

    def test_duplicate_email_conflicts(self, client):
        payload = {"email": "dupe@example.com", "password": "a-good-password-9"}
        assert client.post("/api/auth/register", json=payload).status_code == 201
        assert client.post("/api/auth/register", json=payload).status_code == 409

    def test_short_password_rejected(self, client):
        response = client.post(
            "/api/auth/register",
            json={"email": "short@example.com", "password": "abc"},
        )
        assert response.status_code == 422

    def test_common_password_rejected(self, client):
        response = client.post(
            "/api/auth/register",
            json={"email": "common@example.com", "password": "password"},
        )
        assert response.status_code == 422

    def test_invalid_email_rejected(self, client):
        response = client.post(
            "/api/auth/register",
            json={"email": "not-an-email", "password": "a-good-password-9"},
        )
        assert response.status_code == 422

    def test_login_succeeds(self, client):
        payload = {"email": "login@example.com", "password": "a-good-password-9"}
        client.post("/api/auth/register", json=payload)
        response = client.post("/api/auth/login", json=payload)
        assert response.status_code == 200
        assert "access_token" in response.json()

    def test_wrong_password_rejected(self, client):
        client.post(
            "/api/auth/register",
            json={"email": "wrong@example.com", "password": "a-good-password-9"},
        )
        response = client.post(
            "/api/auth/login",
            json={"email": "wrong@example.com", "password": "a-different-password"},
        )
        assert response.status_code == 401

    def test_unknown_user_same_error_as_wrong_password(self, client):
        """No account enumeration: both paths must look identical."""
        unknown = client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "a-good-password-9"},
        )
        assert unknown.status_code == 401
        assert unknown.json()["detail"] == "Incorrect email or password."

    def test_me_requires_token(self, client):
        assert client.get("/api/auth/me").status_code == 401

    def test_me_returns_user(self, client, auth_headers):
        response = client.get("/api/auth/me", headers=auth_headers)
        assert response.status_code == 200
        assert "@example.com" in response.json()["email"]

    def test_garbage_token_rejected(self, client):
        response = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
        assert response.status_code == 401


class TestAnalyses:
    def test_create_requires_auth(self, client, good_article):
        response = client.post("/api/analyses", json={"text": good_article})
        assert response.status_code == 401

    def test_create_returns_full_result(self, client, auth_headers, good_article):
        response = client.post(
            "/api/analyses",
            json={"text": good_article, "headline": "Inflation eases to 4.2 percent"},
            headers=auth_headers,
        )
        assert response.status_code == 201
        body = response.json()
        assert 0 <= body["score"] <= 100
        assert len(body["result"]["signals"]) == 11
        assert body["result"]["stats"]["word_count"] > 0

    def test_short_text_rejected(self, client, auth_headers):
        response = client.post("/api/analyses", json={"text": "too short"}, headers=auth_headers)
        assert response.status_code == 422

    def test_oversized_text_rejected(self, client, auth_headers):
        response = client.post(
            "/api/analyses", json={"text": "word " * 20000}, headers=auth_headers
        )
        assert response.status_code == 422

    def test_bad_source_url_scheme_rejected(self, client, auth_headers, good_article):
        response = client.post(
            "/api/analyses",
            json={"text": good_article, "source_url": "javascript:alert(1)"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_list_returns_own_analyses(self, client, auth_headers, good_article):
        client.post("/api/analyses", json={"text": good_article}, headers=auth_headers)
        response = client.get("/api/analyses", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["total"] >= 1

    def test_get_one(self, client, auth_headers, good_article):
        created = client.post(
            "/api/analyses", json={"text": good_article}, headers=auth_headers
        ).json()
        response = client.get(f"/api/analyses/{created['id']}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["id"] == created["id"]

    def test_other_users_analysis_is_404_not_403(self, client, good_article):
        """The most important test in the file.

        A 403 would confirm the analysis exists. A 404 says nothing.
        """
        import uuid

        owner = client.post(
            "/api/auth/register",
            json={
                "email": f"owner-{uuid.uuid4().hex[:8]}@example.com",
                "password": "a-good-password-9",
            },
        ).json()
        owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}

        created = client.post(
            "/api/analyses", json={"text": good_article}, headers=owner_headers
        ).json()

        intruder = client.post(
            "/api/auth/register",
            json={
                "email": f"intruder-{uuid.uuid4().hex[:8]}@example.com",
                "password": "a-good-password-9",
            },
        ).json()
        intruder_headers = {"Authorization": f"Bearer {intruder['access_token']}"}

        response = client.get(f"/api/analyses/{created['id']}", headers=intruder_headers)
        assert response.status_code == 404

    def test_delete_own_analysis(self, client, auth_headers, good_article):
        created = client.post(
            "/api/analyses", json={"text": good_article}, headers=auth_headers
        ).json()
        assert (
            client.delete(f"/api/analyses/{created['id']}", headers=auth_headers).status_code == 204
        )
        assert client.get(f"/api/analyses/{created['id']}", headers=auth_headers).status_code == 404

    def test_delete_other_users_analysis_is_404(self, client, good_article):
        import uuid

        owner = client.post(
            "/api/auth/register",
            json={
                "email": f"o2-{uuid.uuid4().hex[:8]}@example.com",
                "password": "a-good-password-9",
            },
        ).json()
        owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
        created = client.post(
            "/api/analyses", json={"text": good_article}, headers=owner_headers
        ).json()

        other = client.post(
            "/api/auth/register",
            json={
                "email": f"o3-{uuid.uuid4().hex[:8]}@example.com",
                "password": "a-good-password-9",
            },
        ).json()
        other_headers = {"Authorization": f"Bearer {other['access_token']}"}

        assert (
            client.delete(f"/api/analyses/{created['id']}", headers=other_headers).status_code
            == 404
        )

    def test_missing_analysis_is_404(self, client, auth_headers):
        assert client.get("/api/analyses/999999", headers=auth_headers).status_code == 404

    def test_pagination_bounds(self, client, auth_headers):
        assert client.get("/api/analyses?limit=0", headers=auth_headers).status_code == 422
        assert client.get("/api/analyses?limit=500", headers=auth_headers).status_code == 422


class TestPreview:
    def test_preview_needs_no_auth(self, client, good_article):
        response = client.post("/api/analyses/preview", json={"text": good_article})
        assert response.status_code == 200
        assert "score" in response.json()

    def test_preview_does_not_persist(self, client, auth_headers, good_article):
        before = client.get("/api/analyses", headers=auth_headers).json()["total"]
        client.post("/api/analyses/preview", json={"text": good_article})
        after = client.get("/api/analyses", headers=auth_headers).json()["total"]
        assert before == after

    def test_preview_rejects_short_text(self, client):
        assert client.post("/api/analyses/preview", json={"text": "nope"}).status_code == 422


class TestSsrfGuard:
    """The URL fetcher is the only outbound call, so it gets its own tests."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost/admin",
            "http://127.0.0.1/",
            "http://127.0.0.1:8000/",
            "http://[::1]/",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.1/",
            "http://192.168.1.1/",
            "http://172.16.0.1/",
        ],
    )
    def test_private_and_loopback_rejected(self, url):
        with pytest.raises(FetchError):
            assert_safe_url(url)

    @pytest.mark.parametrize(
        "url", ["file:///etc/passwd", "ftp://example.com/x", "javascript:alert(1)"]
    )
    def test_non_http_schemes_rejected(self, url):
        with pytest.raises(FetchError):
            assert_safe_url(url)

    def test_public_url_allowed(self):
        # example.com is a stable public host; this only checks the guard,
        # it does not make a request.
        assert_safe_url("https://example.com/article")

    def test_metadata_hostname_rejected(self):
        with pytest.raises(FetchError):
            assert_safe_url("http://metadata.google.internal/computeMetadata/v1/")


class TestHtmlToText:
    def test_strips_tags(self):
        _title, text = html_to_text("<html><body><p>Hello world</p></body></html>")
        assert "Hello world" in text
        assert "<p>" not in text

    def test_extracts_title(self):
        title, _ = html_to_text("<html><head><title>My Story</title></head><body>x</body></html>")
        assert title == "My Story"

    def test_removes_script_content(self):
        _, text = html_to_text("<body><script>alert('x')</script><p>Real text</p></body>")
        assert "alert" not in text
        assert "Real text" in text

    def test_removes_style_content(self):
        _, text = html_to_text("<body><style>.a{color:red}</style><p>Real</p></body>")
        assert "color:red" not in text

    def test_decodes_entities(self):
        _, text = html_to_text("<p>Tom &amp; Jerry &mdash; friends</p>")
        assert "Tom & Jerry" in text
        assert "—" in text

    def test_paragraphs_separated(self):
        _, text = html_to_text("<p>First para</p><p>Second para</p>")
        assert "First para" in text
        assert "Second para" in text
