# API reference

Base URL: `http://127.0.0.1:8000` in development. All request and response
bodies are JSON. Authenticated endpoints take `Authorization: Bearer <token>`.

Interactive docs are at `/docs` when `ENABLE_DOCS=true` and `APP_ENV` is not
`production`.

## Conventions

- **Status codes are meaningful.** `201` on create, `204` on delete, `401` for
  missing or bad auth, `404` for anything you do not own, `409` for a conflict,
  `422` for validation, `429` for rate limiting.
- **Ownership returns 404, not 403.** The API never confirms that someone
  else's analysis exists.
- **Validation errors are one sentence.** Not a nested JSON tree.
- **Rate limit:** 60 requests per 60 seconds per IP by default, across all
  endpoints. Exceeding it returns `429` with a `Retry-After` header.

---

## Health

### `GET /api/health`

No auth. Reports whether the database is actually reachable, not just that the
process started.

```json
{
  "status": "ok",
  "version": "1.0.0",
  "database": "ok",
  "url_fetch_enabled": true
}
```

`status` is `"degraded"` if the database check fails.

---

## Auth

### `POST /api/auth/register`

Creates an account and returns a token immediately, so the client does not have
to log in again.

```json
{ "email": "you@example.com", "password": "at-least-8-chars" }
```

**201**

```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "expires_in": 604800
}
```

Errors: `409` if the email exists, `422` for a bad email, a password under 8
characters, or a password from the common-password list.

### `POST /api/auth/login`

```json
{ "email": "you@example.com", "password": "at-least-8-chars" }
```

**200** — same shape as register.

Errors: `401` with `"Incorrect email or password."` for both a wrong password
and an unknown address. The message is identical on purpose, and the hash is
still computed when the user is missing so response time does not leak whether
the address exists.

### `GET /api/auth/me`

Requires auth.

```json
{ "id": 1, "email": "you@example.com", "created_at": "2026-11-17T00:12:00Z" }
```

---

## Analyses

### `POST /api/analyses`

Requires auth. Analyses text and saves the result.

```json
{
  "text": "The full article body, at least 80 characters…",
  "headline": "Optional headline",
  "source_url": "https://example.com/article"
}
```

`headline` and `source_url` are optional. Supplying a headline enables the
headline-vs-body check; supplying a URL enables the domain check.

**201**

```json
{
  "id": 12,
  "title": "Inflation eases to 4.2 percent",
  "source_url": null,
  "word_count": 150,
  "score": 87.32,
  "band": "strong",
  "confidence": "low",
  "created_at": "2026-11-17T00:12:00Z",
  "result": {
    "score": 87.32,
    "band": { "id": "strong", "label": "Strong signals", "description": "…" },
    "confidence": { "level": "low", "label": "Low", "reason": "150 words. …" },
    "signals": [
      {
        "id": "attribution",
        "label": "Attribution",
        "weight": 0.15,
        "score": 84.0,
        "summary": "3 named-source reference(s) — the claims are checkable.",
        "applies": true,
        "evidence": [
          {
            "label": "Named source",
            "detail": "\"according to\" appears 1×",
            "span": "…according to data released by the Pakistan Bureau…",
            "count": 1
          }
        ]
      }
    ],
    "stats": {
      "word_count": 150,
      "sentence_count": 8,
      "paragraph_count": 4,
      "avg_sentence_words": 18.75,
      "avg_word_length": 4.9,
      "unique_word_ratio": 0.72,
      "exclamation_count": 0,
      "all_caps_count": 0,
      "number_count": 9
    },
    "source_url": null
  }
}
```

Errors: `401` unauthenticated, `422` for text outside the length bounds or a
`source_url` that is not http(s).

### `POST /api/analyses/from-url`

Requires auth. Fetches a URL, analyses it, and saves the result.

```json
{ "url": "https://www.dawn.com/news/1234567" }
```

**201** — same shape as above, with `source_url` set to the final URL after
redirects and `title` taken from the page.

Errors: `422` if the page cannot be fetched, returns an HTTP error, is not text,
has almost no readable content, or resolves to a private address.

### `POST /api/analyses/preview`

**No auth, nothing saved.** This is what the UI calls before you log in.

```json
{ "text": "…", "headline": "…", "source_url": "…" }
```

**200** — returns the `result` object only (no `id`, no `created_at`).

### `POST /api/analyses/preview-url`

**No auth, nothing saved.** The anonymous counterpart to `/from-url`.

```json
{ "url": "https://example.com/article" }
```

**200** — returns the `result` object only.

### `GET /api/analyses`

Requires auth. Lists your analyses, newest first.

Query parameters: `limit` (1–100, default 20), `offset` (default 0).

```json
{
  "items": [
    {
      "id": 12,
      "title": "Inflation eases to 4.2 percent",
      "source_url": null,
      "word_count": 150,
      "score": 87.32,
      "band": "strong",
      "confidence": "low",
      "created_at": "2026-11-17T00:12:00Z"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

The list shape omits the signal payload so the response stays small.

### `GET /api/analyses/{id}`

Requires auth. Returns the full analysis, rebuilt from storage without
re-running the engine.

**404** if it does not exist **or belongs to someone else** — the same response
either way.

### `DELETE /api/analyses/{id}`

Requires auth. **204** on success, **404** if not yours or not found.

---

## Error shape

Validation errors are flattened into one readable sentence:

```json
{
  "detail": "text: Text must be at least 80 characters. Got 12.",
  "code": "validation_error"
}
```

Other errors use FastAPI's standard shape:

```json
{ "detail": "Analysis not found." }
```

---

## Rate limiting

Every endpoint is limited to `RATE_LIMIT_REQUESTS` per
`RATE_LIMIT_WINDOW_SECONDS`, per client IP, using a sliding window.

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 42
```

```json
{ "detail": "Too many requests. Slow down and try again shortly." }
```

The limiter is in-process. Behind N workers the effective limit is N × the
configured value. Redis is the fix, and it is listed as open work rather than
pretended away.

---

## Security headers

Every response carries:

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
Content-Security-Policy: default-src 'self'; …; frame-ancestors 'none'
```
