# Tahqeeq · تحقیق

**Credibility analysis for news text that shows you its evidence.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776ab?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Tests](https://img.shields.io/badge/tests-157%20passing-4ade80)](tests/)
[![Ruff](https://img.shields.io/badge/lint-ruff%20clean-261230)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

---

Every misinformation tool I have used gives you a number and a shrug. "87%
reliable." You cannot check the number, you cannot argue with it, and when it
is wrong you have no idea why.

Tahqeeq does the opposite. It scores **how a piece of news is written** — the
sourcing, the hedging, the hype, the urgency — and then shows you the exact
words behind every point it takes off. If you disagree with the score, you can
disagree with a specific sentence.

**It cannot tell you whether a claim is true.** It has no fact database and no
knowledge base. What it can do is show you whether the writing behaves like
reporting or like persuasion. The app says this on every screen, because a tool
that quietly implies more than it can do is worse than no tool.

---

## What it looks at

Eleven independent detectors, each with a weight, a score, and its own evidence.

| Signal | Weight | What it measures |
|---|---|---|
| **Attribution** | 15% | Named sources vs anonymous "sources say" |
| **Certainty** | 12% | Absolute claims vs hedged language |
| **Sensationalism** | 11% | Exclamation density, ALL-CAPS, high-arousal words |
| **Headline vs body** | 10% | Does the body actually contain the headline's claim |
| **Clickbait** | 10% | Curiosity-gap and listicle constructions |
| **Conspiracy framing** | 9% | "They don't want you to know" |
| **Direct quotes** | 8% | Quotations per 100 words |
| **Source domain** | 7% | Publisher tier, from a static table |
| **Sharing bait** | 7% | "Share before it's deleted" |
| **Quantity precision** | 6% | "Thousands of" vs an actual number |
| **Time precision** | 5% | "Recently" vs a real date |

Weights sum to 1.00. They are judgement calls, not fitted parameters — there is
no training set here, and pretending otherwise would be dishonest.

---

## Features

- **Every score is checkable.** Each signal names the spans it matched, with a
  snippet of the original text.
- **Renormalised, not penalised.** A signal that does not apply (no headline, no
  URL) is dropped and the rest are rescaled. Scoring a missing input as neutral
  50 would drag every analysis toward the middle and make the number meaningless.
- **Honest confidence.** Confidence reflects how much text there was, not how
  sure the model is. A 60-word post gets "very low" and a reason.
- **Paste text or a URL.** URL ingestion strips the page to readable text and
  scores the publisher's domain too.
- **Works before you sign up.** The preview endpoint scores text without saving
  it and needs no account.
- **Saved history.** Logged in, analyses persist with their full signal payload,
  so reopening one shows exactly what you saw the first time.
- **Mobile-first UI.** Vanilla JS, no framework, no build step, loads instantly.
- **SSRF-guarded fetcher.** Private, loopback and link-local addresses are
  rejected after DNS resolution, not by string matching.

---

## Screenshots

| Analyser | Result |
|---|---|
| ![Analyser](screenshots/analyse.png) | ![Result](screenshots/result.png) |

| Signal breakdown | Mobile |
|---|---|
| ![Signals](screenshots/signals.png) | ![Mobile](screenshots/mobile.png) |

---

## Live demo

**Not deployed.** There is no `VERCEL_TOKEN` in the build environment, and
Vercel is the wrong host for this anyway — it needs a persistent filesystem and
a real database, neither of which serverless provides.

`docker compose up --build` is the intended path and takes about a minute. The
exact steps are in [docs/setup.md](docs/setup.md).

---

## Install

```bash
git clone https://github.com/mohdabrarbaloch-arch/day-25-tahqeeq.git
cd day-25-tahqeeq

python -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"

cp .env.example .env
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
# paste that line into .env

uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. SQLite is created on first start; no database
server needed.

### With Docker and PostgreSQL

```bash
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
docker compose up --build
```

Full instructions, configuration table and troubleshooting:
[docs/setup.md](docs/setup.md).

---

## Try it

Paste this into the analyser:

> ISLAMABAD — The Ministry of Finance said on Monday that inflation eased to 4.2
> percent in October, down from 5.1 percent the previous month, according to
> data released by the Pakistan Bureau of Statistics.

It scores in the high 80s, and you can open any signal to see why. Then try:

> SHOCKING!!! You won't BELIEVE what they are hiding about the economy!!!
> Sources say the government is about to DESTROY the rupee. Share this before
> it gets deleted!

Same engine, opposite result, and every point it takes off is named.

---

## How it works

```
text ──▶ normalise ──▶ 11 detectors ──▶ weighted aggregate ──▶ score + band + confidence
                            │
                            └──▶ evidence: the exact spans that produced each score
```

The engine is a **pure function of the text**. No network, no clock, no
randomness. Same input, same output, forever — which is what makes the tests
meaningful and the explanations trustworthy.

Full design, data flow and scaling notes: [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Tests

```bash
pytest
```

**157 tests**, no network, no database server, about a second.

They assert direction and reason rather than exact floats — pinning exact
scores would make the suite a mirror of the implementation instead of a check
on it. The important ones:

- A wire-style article scores more than 25 points above a hype piece.
- A signal that does not apply does not change the score of the ones that do.
- Another user's analysis returns **404, not 403**.
- Eight private/loopback/metadata URLs are all rejected by the SSRF guard.
- `Rs. 1,500` and `U.S. officials` are not split into separate sentences.

## Lint

```bash
ruff check . && ruff format --check .
```

Both clean.

---

## API

| Method | Path | Auth | What it does |
|---|---|---|---|
| `GET` | `/api/health` | — | Liveness + database reachability |
| `POST` | `/api/auth/register` | — | Create an account, get a token |
| `POST` | `/api/auth/login` | — | Log in |
| `GET` | `/api/auth/me` | ✓ | Current user |
| `POST` | `/api/analyses` | ✓ | Analyse text and save |
| `POST` | `/api/analyses/from-url` | ✓ | Fetch a URL, analyse, save |
| `POST` | `/api/analyses/preview` | — | Score text, save nothing |
| `POST` | `/api/analyses/preview-url` | — | Score a URL, save nothing |
| `GET` | `/api/analyses` | ✓ | List your analyses |
| `GET` | `/api/analyses/{id}` | ✓ | Read one |
| `DELETE` | `/api/analyses/{id}` | ✓ | Delete one |

Full reference with request and response bodies: [docs/api.md](docs/api.md).

---

## What it gets wrong

Stated here because it is stated in the app too:

- **Satire and parody.** Well-written satire scores badly, because it uses the
  techniques of bad writing on purpose.
- **Non-English text.** The lexicons are English. Urdu and Roman-Urdu will score
  poorly for reasons that have nothing to do with reliability.
- **Careful liars.** Style is not intent. A skilled propagandist who names
  sources and hedges claims will score well.
- **Short texts.** Under 200 words, treat the score as a hint.
- **Legitimate urgency.** A real emergency alert looks like sharing bait,
  because it is written like one.

Use it as one input. Never as a verdict.

---

## Known limits

- **Rate limiting is per process.** Behind N workers the effective limit is
  N × the configured value. Redis is the fix.
- **`create_all()`, no migrations.** Fine for a first deploy; add Alembic before
  you have data you cannot lose.
- **The domain tier table is static.** It is a hand-written list, not a live
  reputation service. Unknown domains score neutrally.
- **No JavaScript rendering.** Pages that need it to show content will fail with
  a clear message.

---

## Stack

FastAPI · Pydantic v2 · SQLAlchemy 2.0 · SQLite / PostgreSQL · JWT (HS256) ·
bcrypt · httpx · vanilla JS · Docker

---

## License

MIT — see [LICENSE](LICENSE).

Built by [ABraz Baloch](https://github.com/mohdabrarbaloch-arch) as Day 25 of a
30-day build challenge.
