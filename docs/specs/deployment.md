# Deployment — Railway

Goal: get OneView running on a public URL with Postgres, migrations,
seeded data, and a real secret key. Target: live and rehearsed before
the Oct 12 demo.

## Part 1 — Code prep (do BEFORE touching Railway)

These make the app runnable on a server. Commit them first.

### 1.1 Procfile (or Railway start command)

Create a file named `Procfile` (no extension) in the repo root:

    web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    release: alembic upgrade head

- `web`: the server. No --reload in production. Railway provides $PORT.
- `release`: runs BEFORE each deploy goes live — applies migrations so
  the production DB schema is always current.

### 1.2 DATABASE_URL driver prefix (the #1 gotcha)

Railway's Postgres gives a URL like:
    postgresql://user:pass@host:5432/railway

But SQLAlchemy + psycopg 3 needs:
    postgresql+psycopg://user:pass@host:5432/railway

In `app/core/config.py`, normalise it so either form works:

    from pydantic import field_validator

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalise_db_url(cls, v: str) -> str:
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+psycopg://", 1)
        return v

(Use the Pydantic v2 validator style your config already uses.)
This is the single most common first-deploy failure — handle it up front.

### 1.3 Session cookie https in production

Where SessionMiddleware is added (app/main.py), set https_only from the
environment so the demo over HTTPS keeps sessions:

    https_only = settings.ENVIRONMENT == "production"
    app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY,
                       https_only=https_only, same_site="lax")

### 1.4 Dependencies Railway can read

Railway's Python builder reads pyproject.toml + uv.lock (it supports uv).
Confirm uv.lock is committed. If the build can't resolve deps, export a
requirements.txt as a fallback:

    uv export --no-hashes --format requirements-txt > requirements.txt

Commit it.

### 1.5 Confirm the SECRET_KEY guard

The startup guard should refuse to boot in production on the default
"change-me". This is correct and intended — it forces a real key to be
set (Part 2). Do not remove it.

## Part 2 — Railway setup (the clicking)

1. Go to railway.app, sign up / log in with GitHub (connects your repos).
2. New Project → Deploy from GitHub repo → select `oneview_analytics`.
3. In the project, click "+ New" → Database → PostgreSQL. Railway
   provisions it and exposes a DATABASE_URL variable to the project.
4. Click the app service → Variables tab. Add:
   - SECRET_KEY = <a real one: python -c "import secrets;
     print(secrets.token_urlsafe(32))">
   - ENVIRONMENT = production
   - DATABASE_URL = ${{Postgres.DATABASE_URL}}  (reference the Postgres
     service's variable — Railway's variable-reference syntax)
5. Settings tab → confirm the start command picks up the Procfile, or
   set it to the `web:` line manually.
6. Deploy. Railway builds, runs the release command (migrations), starts
   the app. Watch the build + deploy logs.

## Part 3 — Seed the production database

The deployed DB has schema (from migrations) but no data. Seed it once.

Railway → app service → open a shell (or run one-off commands), and run:

    python -m app.seed                          # reference data (papers, topics, taxonomy)
    python -m app.seed.demo_attempts            # demo attempts
    python -m app.seed.set_password <username> <password>   # real login

The point: the production DB needs the same seed your local DB has, plus
a real password on the demo student.

## Part 4 — Verify the live site

1. Open the public URL Railway gives you (…up.railway.app).
2. You should hit /login. Log in with the demo credentials.
3. Walk all three screens: both Overview panels populate, Record saves,
   Topic Analysis drills down.
4. Record a paper on the LIVE site → confirm it appears in Overview.
   This proves the full loop works in production.

## The failures to expect (all config, not code)

| Symptom | Cause | Fix |
|---|---|---|
| Build fails on deps | Railway can't read uv | commit requirements.txt (1.4) |
| App boots then crashes, "could not connect" | DATABASE_URL prefix | the validator in 1.2 |
| Boots then exits with secret-key error | SECRET_KEY still default | set it in Variables (Part 2.4) — the guard working as intended |
| Login works, session lost on next click | https_only mismatch | 1.3 |
| 500 on every page | migrations didn't run | check release command ran in deploy logs |
| Pages load but empty | DB not seeded | Part 3 |

Every one of these is environment/config and fixable in minutes once
identified. None are code bugs.