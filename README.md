# Checkout & Rewards Service

A reliable ecommerce checkout + rewards backend: carts, inventory, concurrency-safe
checkout with idempotent retries, single-use discount coupons granted every *n*-th order,
and an admin report that reconciles with the data.

- **Backend:** FastAPI (async) + SQLAlchemy 2 + asyncpg
- **Database:** PostgreSQL
- **Frontend:** React (Vite) — a small demo UI for the full flow
- **Design rationale & trade-offs:** see [`DECISIONS.md`](./DECISIONS.md)
- **Original assignment brief:** [`ASSIGNMENT.md`](./ASSIGNMENT.md)

Approximate time spent: ~5 hours.

---

## Quick start (Docker Compose)

Requires Docker Desktop (with the engine running).

```bash
cp .env.example .env
docker compose up --build
```

This starts three services:

| Service  | URL                             | Notes |
|----------|---------------------------------|-------|
| Postgres | `localhost:5432`                | data persisted in a named volume |
| Backend  | http://localhost:8000           | OpenAPI docs at http://localhost:8000/docs |
| Frontend | http://localhost:5173           | demo UI |

On startup the backend creates the schema and seeds **6 products** (one deliberately
low-stock: *Limited Edition Vinyl*, 3 units) so you can exercise oversell/concurrency.

Configuration (in `.env`): `COUPON_ORDER_INTERVAL` (**n**), `COUPON_PERCENT` (**x**),
`ADMIN_TOKEN`.

---

## Running the tests

The suite focuses on the hard invariants (concurrency, idempotency, money, reconciliation)
and uses a dedicated `*_test` database so it never clobbers app data.

```bash
# against the Compose Postgres
docker compose run --rm backend pytest -v
```

Or locally (needs Python 3.11+ and a reachable Postgres):

```bash
cd backend
pip install -r requirements.txt
DATABASE_URL=postgresql+asyncpg://uniblox:uniblox@localhost:5432/uniblox pytest -v
```

What the tests prove:

- `test_checkout_concurrency.py` — 5 concurrent checkouts against 3 units: exactly 3 succeed, inventory lands at 0, never negative. *(the required non-happy-path test)*
- `test_coupons.py` — one coupon redeemed by only one of two concurrent checkouts; a failed checkout does **not** consume the coupon; milestone generation is once-per-milestone; admin gating.
- `test_idempotency.py` — same `Idempotency-Key` / same cart (sequential **and** concurrent) ⇒ one order, inventory charged once.
- `test_report.py` — report reconciles (`net == gross − discounts == Σ totals`) and repeated calls don't mutate state.
- `test_cart_validation.py` — invalid product/quantity rejected; empty-cart and checked-out-cart behavior.
- `test_money.py` — half-up rounding and non-negative totals.

---

## API

Base URL `http://localhost:8000`. Interactive docs at `/docs`. All errors share the shape
`{ "error": { "code", "message", "details" } }`.

### Public

| Method | Path | Body | Success | Notable errors |
|--------|------|------|---------|----------------|
| `GET` | `/products` | — | `200` list | — |
| `POST` | `/carts` | — | `201` cart | — |
| `GET` | `/carts/{id}` | — | `200` cart | `404 CART_NOT_FOUND` |
| `POST` | `/carts/{id}/items` | `{product_id, quantity}` | `200` cart | `404 PRODUCT_NOT_FOUND`, `422 VALIDATION_ERROR` |
| `PATCH` | `/carts/{id}/items/{product_id}` | `{quantity}` | `200` cart | `404 CART_ITEM_NOT_FOUND` |
| `DELETE` | `/carts/{id}/items/{product_id}` | — | `200` cart | `404 CART_ITEM_NOT_FOUND` |
| `POST` | `/carts/{id}/checkout` | `{coupon_code?}` + header `Idempotency-Key?` | `200` order | `400 CART_EMPTY`, `409 INSUFFICIENT_INVENTORY`, `409 COUPON_INVALID_OR_REDEEMED` |
| `GET` | `/orders/{id}` | — | `200` order | `404 ORDER_NOT_FOUND` |

### Admin (require header `X-Admin-Token: <ADMIN_TOKEN>`)

| Method | Path | Success | Notable errors |
|--------|------|---------|----------------|
| `POST` | `/admin/coupons/generate` | `201` coupon | `409 MILESTONE_NOT_REACHED`, `409 COUPON_ALREADY_GENERATED`, `401 UNAUTHORIZED` |
| `GET` | `/admin/report` | `200` report (read-only) | `401 UNAUTHORIZED` |

Money is returned as integer `*_cents` **and** a formatted `*_display` string; clients
never parse money from a float.

---

## Example: full flow with curl

```bash
# 1. Create a cart
CART=$(curl -s -XPOST localhost:8000/carts | python -c "import sys,json;print(json.load(sys.stdin)['id'])")

# 2. Add 1x the low-stock product (id 5)
curl -s -XPOST localhost:8000/carts/$CART/items -H 'content-type: application/json' \
  -d '{"product_id":5,"quantity":1}'

# 3. Checkout (idempotent — safe to retry with the same key)
curl -s -XPOST localhost:8000/carts/$CART/checkout \
  -H 'content-type: application/json' -H 'Idempotency-Key: demo-1' -d '{}'

# 4. Admin report
curl -s localhost:8000/admin/report -H 'X-Admin-Token: dev-admin-token'
```

### Concurrency smoke check (oversell protection)

With the low-stock product (id 5, 3 units), fire several checkouts at once and observe
that only three succeed and inventory never goes negative:

```bash
for i in 1 2 3 4 5; do
  C=$(curl -s -XPOST localhost:8000/carts | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
  curl -s -XPOST localhost:8000/carts/$C/items -H 'content-type: application/json' -d '{"product_id":5,"quantity":1}' >/dev/null
  (curl -s -o /dev/null -w "%{http_code}\n" -XPOST localhost:8000/carts/$C/checkout -H 'content-type: application/json' -d '{}' &)
done; wait
```

---

## Project layout

```
backend/   FastAPI app (app/), services enforce invariants, tests/ prove them
frontend/  React + Vite demo UI
docker-compose.yml   postgres + backend + frontend
DECISIONS.md         invariants, trade-offs, concurrency/idempotency/money, AI use
ASSIGNMENT.md        the original take-home brief
```

See [`DECISIONS.md`](./DECISIONS.md) for the invariant list, the checkout transaction
walkthrough, and how the design scales to multiple instances.
