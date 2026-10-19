# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A checkout + rewards backend (FastAPI async + SQLAlchemy 2 + asyncpg + PostgreSQL) with a
small React (Vite) demo UI. It is a take-home graded on **correctness under retries,
concurrency, inventory changes, and coupon contention** — not CRUD. The original brief is
`ASSIGNMENT.md`; design rationale is `DECISIONS.md`; verification is `TEST_REPORT.md`.

## Commands

```bash
# Run everything (intended path; needs Docker + virtualization)
cp .env.example .env
docker compose up --build          # Postgres, backend :8000 (docs at /docs), frontend :5173

# Run the test suite (authoritative proof of the invariants)
docker compose run --rm backend pytest -v
# ...or locally against any reachable Postgres:
cd backend && DATABASE_URL=postgresql+asyncpg://<user>:<pass>@<host>:<port>/<db> pytest -v
pytest -v tests/test_coupons.py                                   # one file
pytest -v tests/test_coupons.py::test_failed_checkout_does_not_consume_coupon  # one test

# Run backend / frontend locally without Docker
cd backend && DATABASE_URL=postgresql+asyncpg://... uvicorn app.main:app --port 8000
cd frontend && VITE_API_BASE=http://localhost:8000 npm run dev
```

There is no lint/build step for the backend. Frontend production build: `cd frontend && npm run build`.

## Architecture — the big picture

**Invariants are enforced in PostgreSQL, never in Python "check-then-act" logic.** This is the
single most important thing to preserve when changing code. Application-level validation races
under concurrency; the database does not. Every correctness guarantee traces to one of:
row locks (`SELECT … FOR UPDATE`), guarded conditional UPDATEs (`… WHERE inventory >= :q`),
or UNIQUE constraints. See the invariant list at the top of `DECISIONS.md`.

**Request flow:** `app/routers/*` (thin HTTP layer, Pydantic schemas) → `app/services/*`
(all business logic + transaction orchestration) → `app/models.py` (ORM + DB constraints).
Routers own the DB session (via `get_session`) and `commit`; services take a session and
`flush` but generally do **not** commit (so a raised error rolls back the whole operation).
`checkout_service` is the exception-driven heart: it builds the order, claims the coupon, and
decrements inventory in one transaction — any raise unwinds all of it.

**`app/services/checkout_service.py` is the file to read first.** The step order is deliberate
and documented inline: idempotency fast-path → lock cart `FOR UPDATE` (return existing order if
already checked out) → lock products `FOR UPDATE ORDER BY id` (stable order = deadlock-free) →
snapshot prices → conditional coupon claim → guarded inventory decrement → persist. Do not
reorder these or move the commit into the service.

**Idempotency has two layers:** `orders.cart_id` UNIQUE (a cart yields at most one order, even
without a key) and `orders.idempotency_key` UNIQUE (the `Idempotency-Key` header fast-path for
lost-response retries). Both matter; don't remove either.

**Money is integer cents everywhere** — DB columns (`*_cents` BIGINT), services, and API. The
only rounding is a percentage discount, done with `Decimal`/`ROUND_HALF_UP` in `app/money.py`
and clamped so totals never go negative. Never introduce float math on money. API responses
also carry `*_display` strings via Pydantic `@computed_field` (plain `@property` will NOT
serialize in Pydantic v2).

**Orders are immutable snapshots:** `order_items` copy product name + unit price at checkout, so
later product changes never rewrite history. The admin report aggregates from these snapshots,
not from live products, and is strictly read-only (`report_service.py`).

**Coupons:** generation is admin-triggered and lazy. Milestone = `(order_count // n) * n`;
insertion uses `ON CONFLICT (milestone) DO NOTHING` against `UNIQUE(milestone)` so it's
once-per-milestone even concurrently. Redemption is a single conditional UPDATE
(`active → redeemed`); the loser of a race gets 0 rows and the checkout fails cleanly.

**Errors:** every client-facing failure is a `DomainError` subclass in `app/errors.py` with a
stable machine `code`, HTTP `status`, and optional `details`; `main.py` renders them all as
`{ "error": { "code", "message", "details" } }`. Add new failures as `DomainError` subclasses,
not ad-hoc `HTTPException`s.

## Configuration & conventions

- Reward rule and admin boundary come from env (`app/config.py`): `COUPON_ORDER_INTERVAL` (n),
  `COUPON_PERCENT` (x), `ADMIN_TOKEN`. Admin endpoints (`/admin/*`) require header
  `X-Admin-Token`; real auth is intentionally out of scope.
- Schema is created on startup via `Base.metadata.create_all` + an idempotent product seed
  (`app/seed.py`) — **there is no Alembic**. Changing `models.py` changes the live schema on
  next boot; a fresh DB (or dropped tables) is the migration mechanism for now.

## Tests

- `backend/tests/conftest.py` runs the whole suite on a **single session-scoped event loop**
  (required so the one async engine/pool isn't bound to a different loop) and drives the real
  ASGI app through `httpx.ASGITransport`. It auto-creates a dedicated `<db>_test` database and
  truncates tables between tests, so it never touches real data.
- Concurrency tests use `asyncio.gather` over real HTTP requests, each on its own DB
  connection — this produces genuine contending transactions, not mocks. When adding a
  concurrency test, follow this pattern (see `test_checkout_concurrency.py`) rather than calling
  services directly.
