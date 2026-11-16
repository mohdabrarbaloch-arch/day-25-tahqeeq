# Architecture — Tahqeeq

Tahqeeq scores **how a piece of news text is written**, not whether it is true.
That distinction drives every decision below, and the app says it out loud on
every screen.

## The one-sentence version

Text comes in, it is normalised once, eleven independent detectors each look at
one property of the writing and return a score plus the exact spans that
produced it, and a weighted aggregate turns those into a single number with a
band and a confidence level.

## System diagram

```
┌──────────────┐
│   Browser    │  vanilla JS SPA, no build step, mobile-first
└──────┬───────┘
       │ JSON over HTTPS
┌──────▼──────────────────────────────────────────────────┐
│  FastAPI  (app/main.py)                                 │
│  ├── middleware: CORS · security headers · rate limit   │
│  ├── routers/auth.py       register / login / me        │
│  ├── routers/analyses.py   create / from-url / list /   │
│  │                         get / delete / preview       │
│  └── routers/health.py     liveness + readiness         │
└──────┬──────────────────────────────┬───────────────────┘
       │                              │
┌──────▼──────────────┐      ┌────────▼──────────────────┐
│  engine/            │      │  SQLAlchemy 2.0           │
│  pure functions     │      │  SQLite (dev)             │
│  no I/O, no network │      │  PostgreSQL (prod)        │
│  no clock, no random│      └───────────────────────────┘
└──────┬──────────────┘
       │
┌──────▼──────────────────────────────────────────────────┐
│  text.py      normalise · sentence split · stats        │
│  lexicon.py   curated word and phrase lists             │
│  signals.py   11 detectors, each → Signal               │
│  scoring.py   weighted aggregate → score, band, conf.   │
│  domains.py   static domain tier table                  │
└─────────────────────────────────────────────────────────┘
```

The engine is deliberately a **pure function of the text**. No network calls, no
clock reads, no randomness. Given the same input it returns the same output
forever, which is what makes the tests meaningful and the explanations
trustworthy.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| API | FastAPI + Pydantic v2 | Typed request/response, free OpenAPI, fast |
| ORM | SQLAlchemy 2.0 (`Mapped` style) | SQLite locally, Postgres in prod, one codebase |
| Auth | JWT (HS256) + bcrypt | Stateless, no session store to run |
| Frontend | Vanilla JS + CSS | No build step, no framework churn, loads instantly |
| Fetch | httpx | Timeouts and size caps are first-class |
| Tests | pytest | 60+ tests, no network, no DB server |
| Lint | ruff (check + format) | One tool, fast, opinionated |

## Data flow — one analysis

1. **Ingest.** Either `POST /api/analyses` with `{text, headline?, source_url?}`
   or `POST /api/analyses/from-url` with `{url}`.
2. **URL path only:** the fetcher resolves the host, rejects private, loopback
   and link-local addresses (SSRF guard), follows redirects with a cap, streams
   at most `URL_FETCH_MAX_BYTES`, and strips the HTML down to readable text.
3. **Normalise.** Unicode NFKC, collapse whitespace, split paragraphs.
4. **Detect.** Each of the eleven detectors reads the normalised document and
   returns a `Signal`: an id, a weight, a 0–100 score, a one-line summary, and a
   tuple of `Evidence` items naming the exact spans it matched.
5. **Aggregate.** Weighted mean over the signals that apply. The domain signal
   only applies when a URL was supplied, so the remaining weights are
   renormalised rather than the score being silently penalised.
6. **Band + confidence.** The score maps to one of five bands. Confidence is
   derived from word count — a 40-word post cannot be judged the way a
   1,200-word article can, and pretending otherwise would be dishonest.
7. **Persist.** The full signal payload is stored as JSON alongside the score,
   so a saved analysis can be re-read later without re-running the engine.

## The scoring model

| Signal | Weight | What it measures |
|---|---|---|
| `attribution` | 0.15 | Named sources vs anonymous "sources say" |
| `certainty` | 0.12 | Absolute claims vs hedged language |
| `sensationalism` | 0.11 | Exclamation density, ALL-CAPS, high-arousal words |
| `headline_body` | 0.10 | Does the body actually contain the headline's claim |
| `clickbait` | 0.10 | Curiosity-gap and listicle constructions |
| `conspiracy` | 0.09 | "They don't want you to know" framing |
| `quotes` | 0.08 | Direct quotations per 100 words |
| `domain` | 0.07 | Source domain tier (only when a URL is given) |
| `sharing_bait` | 0.07 | "Share before it's deleted" urgency |
| `quantity_vagueness` | 0.06 | "Thousands of" vs an actual number |
| `temporal_vagueness` | 0.05 | "Recently" vs a real date |

Weights sum to 1.00. Each is a judgement call, not a fitted parameter — there is
no training set here, and the README says so.

## Storage

```
users      id · email (unique) · password_hash · created_at
analyses   id · user_id → users.id · title · source_url · text
           word_count · score · band · confidence
           signals (JSON) · created_at
```

`signals` is stored as JSON rather than a child table because it is written once
and read whole — normalising it would add joins for no query benefit.

## Scaling notes

- **Stateless API.** Any number of instances behind a load balancer; the only
  shared state is the database.
- **Rate limiting is in-process.** Behind N workers the effective limit is N ×
  the configured value. Redis with a sliding window is the fix, and it is listed
  as open work rather than pretended away.
- **The engine is CPU-bound and cheap.** Roughly 1 ms for a 1,000-word article.
  It does not need a queue. If a heavier model is added later, the natural split
  is: persist the analysis as `pending`, enqueue, and let the client poll — the
  schema already has room for a status column.
- **URL fetching is the only outbound call.** It is bounded by timeout, byte cap
  and redirect cap, and can be switched off entirely with `ALLOW_URL_FETCH=false`.

## Security

- Passwords hashed with bcrypt at cost 12; the cost is configurable.
- JWT signed with `SECRET_KEY`; the app **refuses to boot in production** with
  the default development key.
- Owner-scoped queries return **404, not 403**, so the API never confirms that
  someone else's analysis exists.
- SSRF guard on the URL fetcher: private, loopback, link-local and reserved
  ranges are rejected after DNS resolution, not just by string matching.
- Security headers on every response: `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, `Content-Security-Policy`,
  `Permissions-Policy`.
- All secrets come from the environment. Nothing is hardcoded.

## Known limits

Stated here because they are stated in the UI too:

- It cannot tell you whether a claim is **true**. It has no knowledge base and
  no fact database.
- It is tuned on English-language news conventions. Urdu and Roman-Urdu text
  will score poorly for reasons that have nothing to do with reliability.
- Satire and parody are not detected. Well-written satire will score badly.
- A careful liar writes like a journalist. Style is not intent.
