# Setup

Two ways to run it: locally with Python, or with Docker Compose. The local path
uses SQLite and needs no database server, which is the fastest way to see it
working.

## Requirements

- Python 3.11 or newer
- (optional) Docker and Docker Compose, for the Postgres path

## Local, SQLite, five minutes

```bash
git clone https://github.com/mohdabrarbaloch-arch/day-25-tahqeeq.git
cd day-25-tahqeeq

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -e ".[dev]"

cp .env.example .env
```

Generate a real signing key and put it in `.env`:

```bash
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
```

Then run it:

```bash
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. The API docs are at `/docs` in development.

The database file (`tahqeeq.db`) is created on first start. Delete it to reset.

## Docker Compose, with PostgreSQL

```bash
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
docker compose up --build
```

That starts Postgres, waits for it to be healthy, then starts the app on
<http://127.0.0.1:8000>. Data lives in the `pgdata` volume.

To stop: `docker compose down`. To also drop the data: `docker compose down -v`.

## Configuration

Every setting is an environment variable, documented in `.env.example`. The
ones that matter most:

| Variable | Default | What it does |
|---|---|---|
| `APP_ENV` | `development` | `production` disables `/docs` and enforces a real `SECRET_KEY` |
| `SECRET_KEY` | dev placeholder | JWT signing key. **The app refuses to boot in production with the default.** |
| `DATABASE_URL` | `sqlite:///./tahqeeq.db` | Any SQLAlchemy URL |
| `BCRYPT_ROUNDS` | `12` | Password hashing cost |
| `ALLOW_URL_FETCH` | `true` | Set `false` to disable all outbound fetching |
| `URL_FETCH_MAX_BYTES` | `2000000` | Hard cap on a fetched page |
| `MAX_TEXT_CHARS` | `40000` | Longest text accepted |
| `MIN_TEXT_CHARS` | `80` | Shortest text accepted |
| `RATE_LIMIT_REQUESTS` | `60` | Requests per window, per IP |

## Running the tests

```bash
pytest
```

157 tests, no network, no database server, about a second. They use a
throwaway SQLite file and a low bcrypt cost.

## Linting and formatting

```bash
ruff check .
ruff format --check .
```

Both must pass cleanly. `ruff format .` fixes formatting in place.

## Production notes

- Set `APP_ENV=production` and a real `SECRET_KEY`. The app will not start
  otherwise, on purpose.
- Put it behind a reverse proxy that terminates TLS. The app sets
  `X-Forwarded-*`-aware behaviour via `--proxy-headers`.
- `create_all()` runs on startup. That is fine for a first deploy; add Alembic
  before you have data you cannot lose.
- Rate limiting is per process. Behind N workers the effective limit is N ×
  the configured value. Redis is the fix.

## Troubleshooting

**"SECRET_KEY is still the development default"** — you set `APP_ENV=production`
without a real key. Generate one as shown above.

**"That host resolves to a private address"** — the SSRF guard rejected the URL.
That is the guard working. It blocks loopback, private and link-local ranges.

**"That page had almost no readable text"** — the page needs JavaScript to
render. The fetcher does not run JavaScript, by design.
