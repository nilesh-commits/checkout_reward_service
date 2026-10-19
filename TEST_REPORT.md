# Test & Verification Report

**Project:** Checkout & Rewards Service
**Stack:** FastAPI (async) · PostgreSQL · React (Vite)
**Status:** ✅ All 17 automated tests pass against a real PostgreSQL 16; full manual UI flow verified.

This report explains **what** was tested, **how** (browser vs. non-browser), and **why** the
non-browser tests are written the way they are — especially the concurrency cases, which are
the heart of the assignment.

---

## 1. Testing philosophy

The assignment is graded on correctness under **retries, concurrency, inventory changes, and
coupon contention** — not CRUD. A test suite that only calls each endpoint once in a happy-path
sequence was explicitly called out as insufficient. So verification is split by what each layer
can actually prove:

| Layer | Good at proving | Blind to |
|-------|-----------------|----------|
| **Browser (manual UI)** | The functional happy path and that errors surface clearly to a user | Simultaneity, raw/invalid requests, exact HTTP status codes, DB-level invariants |
| **Non-browser (automated + curl)** | Concurrency, idempotency, money precision, transactional rollback, strict API contract, auth boundary | Nothing material — this is where correctness is actually guaranteed |

The guiding principle of the implementation is that **invariants are enforced in the database**
(row locks + guarded conditional UPDATEs + UNIQUE constraints), not in Python-level "check then
act" logic that races. The non-browser tests are designed to attack exactly those invariants.

---

## 2. Browser tests (manual, via the React UI at `http://localhost:5173`)

These confirm the end-to-end functional behavior a human would experience. Each maps to an
assignment requirement.

| # | Scenario (click path) | Requirement verified | Expected result |
|---|------------------------|----------------------|-----------------|
| B1 | Shop → Add item → Cart → change qty / remove → Checkout | Cart CRUD, prices & totals, order creation | Order created with correct totals |
| B2 | Order tab after checkout | Order retains purchase-time snapshot | Item name/price frozen on the order |
| B3 | Add 4× *Limited Edition Vinyl* (3 in stock) → Checkout | Must not sell more than available | Red toast `INSUFFICIENT_INVENTORY`, no order |
| B4 | Admin → Generate coupon before 5 orders | Coupon only at milestone | `MILESTONE_NOT_REACHED` |
| B5 | Place 5 orders → Admin → Generate; then Generate again | Generate once per milestone | 1st: coupon `milestone 5, 10%`; 2nd: `COUPON_ALREADY_GENERATED` |
| B6 | Use coupon at checkout; then reuse it | Redeemable once | 1st: discount applied; 2nd: `COUPON_INVALID_OR_REDEEMED` |
| B7 | Admin report; refresh twice | Report reconciles, read-only | `Net = Gross − Discounts`; numbers stable |
| B8 | Any failure | Distinguishable, useful errors | Machine error code shown in toast |

**What the browser cannot test:** it issues one well-formed request at a time, so every
race condition, the `Idempotency-Key` retry, invalid-input paths, exact status codes, the
admin `401`, and DB-level rollback are **out of reach** — see §3.

---

## 3. Non-browser tests (automated — `pytest`, 17 tests)

Run:

```bash
cd backend
DATABASE_URL=postgresql+asyncpg://<user>:<pass>@<host>:<port>/<db> pytest -v
# (Docker: docker compose run --rm backend pytest -v)
```

Result: **17 passed**. The harness (`backend/tests/conftest.py`) runs the whole suite on a
single event loop against a dedicated `*_test` database, and drives the **real ASGI app** via
`httpx.ASGITransport`. Each request gets its own DB session/connection from the pool, so
`asyncio.gather` produces **genuinely concurrent transactions contending on the same Postgres
row locks** — not mocked concurrency.

### 3.1 Concurrency & idempotency (the critical set)

| Test (`file::name`) | What it fires | What it proves |
|---------------------|---------------|----------------|
| `test_checkout_concurrency::test_concurrent_checkouts_do_not_oversell` | 5 checkouts in parallel on a 3-unit product | Exactly 3 succeed, 2 get `409`, inventory ends at 0 — never negative |
| `test_coupons::test_coupon_redeemed_by_only_one_of_two_concurrent_checkouts` | 2 checkouts in parallel, same coupon | Exactly one `200` (discount applied), one `409 COUPON_INVALID_OR_REDEEMED` |
| `test_idempotency::test_concurrent_retries_same_cart_create_one_order` | 2 concurrent checkouts of one cart, same `Idempotency-Key` | Same order id, inventory charged once |
| `test_idempotency::test_idempotency_key_returns_same_order` | Sequential retry with same key | Same order id, inventory charged once |
| `test_idempotency::test_reposting_same_cart_returns_same_order` | Re-POST the same cart, no key | Same order id (cart-level idempotency) |
| `test_coupons::test_failed_checkout_does_not_consume_coupon` | Checkout that oversells **with** a valid coupon | `409`; coupon remains `active` (transaction rolled back) |

### 3.2 Business rules

| Test | Proves |
|------|--------|
| `test_coupons::test_milestone_generation_is_once_per_milestone` | `MILESTONE_NOT_REACHED` before n; coupon at milestone 5; `COUPON_ALREADY_GENERATED` on repeat |
| `test_coupons::test_admin_requires_token` | Admin endpoints return `401 UNAUTHORIZED` without the token |
| `test_report::test_report_reconciles_and_is_read_only` | `net == gross − discounts == Σ totals`; quantities match; repeated calls don't mutate |

### 3.3 Money

| Test | Proves |
|------|--------|
| `test_money::test_discount_rounds_half_up` | 10% of 1005¢ = 101¢ (half-up), of 1004¢ = 100¢ |
| `test_money::test_discount_never_exceeds_subtotal` | 100%+ discount clamps to subtotal → total ≥ 0 |
| `test_money::test_zero_cases` / `test_format_cents` | Zero handling and display formatting |

### 3.4 Validation & API contract

| Test | Proves |
|------|--------|
| `test_cart_validation::test_unknown_product_rejected` | `404 PRODUCT_NOT_FOUND` |
| `test_cart_validation::test_non_positive_quantity_rejected` | `422 VALIDATION_ERROR` |
| `test_cart_validation::test_checkout_empty_cart_rejected` | `400 CART_EMPTY` |
| `test_cart_validation::test_cannot_modify_checked_out_cart` | `422` modifying a checked-out cart |

---

## 4. The logic behind the non-browser (concurrency) cases

This section explains **why each concurrency test passes** — i.e. the mechanism under test.
All of it lives in `backend/app/services/checkout_service.py` and the schema in
`backend/app/models.py`.

### 4.1 The checkout transaction

Checkout runs as **one database transaction** (READ COMMITTED), committed by the router only on
success. Any exception rolls the entire thing back. The ordered steps:

1. **`Idempotency-Key` fast path** — if a prior order exists for the key, return it.
2. **`SELECT … FOR UPDATE` the cart row** — serializes concurrent checkouts of the *same* cart.
   If the cart is already `checked_out`, return its existing order (cart-level idempotency).
3. **`SELECT … FOR UPDATE` the product rows, `ORDER BY id`** — locks every involved product in a
   stable order, which prevents deadlocks between checkouts touching overlapping products.
4. **Snapshot prices**, compute the subtotal in integer cents.
5. **Coupon claim** — a single conditional UPDATE:
   `UPDATE coupons SET status='redeemed', redeemed_order_id=:id WHERE code=:code AND status='active'`.
6. **Inventory decrement** — a guarded UPDATE per line:
   `UPDATE products SET inventory = inventory - :q WHERE id=:id AND inventory >= :q`.
7. **Insert** the order + snapshot line items; mark the cart `checked_out`.

### 4.2 Why "no oversell under concurrency" holds

Two checkouts for the last units run as separate transactions. Both take the product row lock in
step 3 — so they **serialize** on that row: one proceeds, the other waits. The winner's guarded
UPDATE in step 6 (`WHERE inventory >= :q`) succeeds and lowers stock; when the loser proceeds, its
identical UPDATE now matches **0 rows** because the guard fails. Zero rows affected ⇒ the code
raises `INSUFFICIENT_INVENTORY` ⇒ rollback. The decision and the write are the *same atomic SQL
statement*, so there is no check-then-act gap. A `CHECK (inventory >= 0)` constraint is the final
backstop. → *proven by `test_concurrent_checkouts_do_not_oversell`.*

### 4.3 Why a coupon can't be double-redeemed

The claim in step 5 is atomic: only the transaction whose UPDATE flips `active → redeemed` gets a
row back. A concurrent checkout's UPDATE matches 0 rows (status already `redeemed`) and raises
`COUPON_INVALID_OR_REDEEMED`. Because the whole checkout is one transaction, a **failure anywhere
after the claim rolls the redemption back** — so a coupon is never "lost" by a checkout that
ultimately fails. → *proven by `test_coupon_redeemed_by_only_one_of_two_concurrent_checkouts` and
`test_failed_checkout_does_not_consume_coupon`.*

### 4.4 Why retries don't create duplicate orders

Two layers:
- **`orders.cart_id` is UNIQUE** and the cart is locked + flipped to `checked_out` inside the
  transaction, so a second checkout of the same cart returns the first order rather than making
  another — regardless of whether the client sent a key.
- **`orders.idempotency_key` is UNIQUE** and checked first, giving a fast path for the classic
  "client timed out and retried" case.
Under concurrent retries, the cart `FOR UPDATE` lock serializes them: the second sees
`checked_out` and returns the same order. → *proven by the three `test_idempotency` tests.*

### 4.5 Why "generate coupon once per milestone" holds

Milestone = `(order_count // n) * n`. Generation does
`INSERT … ON CONFLICT (milestone) DO NOTHING` against a `UNIQUE(milestone)` constraint, so even
concurrent admin requests can't create two coupons for the same block of orders. →
*proven by `test_milestone_generation_is_once_per_milestone`.*

### 4.6 Money

All amounts are integer cents end to end; the only rounding (a percentage discount) uses
`Decimal` with `ROUND_HALF_UP`, then clamps the discount to the subtotal so totals can never go
negative. No float ever touches money. → *proven by the `test_money` tests.*

---

## 5. Requirements → test-type coverage matrix

| Requirement (from the brief) | Browser | Automated | curl / DB |
|------------------------------|:------:|:---------:|:---------:|
| Products/inventory, invalid input rejected | B1 | ✅ §3.4 | ✅ |
| Cart CRUD, prices & totals | B1 | — | ✅ |
| Price/availability change before checkout | — | — | ✅ (psql) |
| Checkout creates an order; order is a snapshot | B1–B2 | ✅ | — |
| Retry doesn't duplicate (idempotency) | partial* | ✅ §3.1 | ✅ |
| **Concurrent checkouts don't oversell** | ✗ | ✅ §3.1 | ✅ (parallel curl) |
| Money without float; total ≥ 0 | — | ✅ §3.3 | — |
| Distinguishable, useful errors | B8 | ✅ §3.4 | ✅ |
| Coupon only at milestone, once per milestone | B4–B5 | ✅ §3.2 | ✅ |
| Coupon redeemed once; **not by two concurrent checkouts** | B6 / ✗ | ✅ §3.1 | — |
| Coupon not consumed by a failed checkout | — | ✅ §3.1 | — |
| Admin report reconciles, read-only | B7 | ✅ §3.2 | ✅ |
| Admin boundary (401 without token) | ✗ | ✅ §3.2 | ✅ |

\* The UI gives cart-level idempotency but can't send an `Idempotency-Key` or reproduce a
"lost-response" retry.

---

## 6. How to reproduce

**Automated suite** (the authoritative proof):
```bash
docker compose up --build            # or run Postgres + backend locally
docker compose run --rm backend pytest -v
# => 17 passed
```

**Live concurrency demo** (watch a race resolve) — fire 5 parallel checkouts at the 3-unit product:
```bash
B=http://localhost:8000
for i in 1 2 3 4 5; do
  C=$(curl -s -XPOST $B/carts | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
  curl -s -XPOST $B/carts/$C/items -H 'content-type: application/json' -d '{"product_id":5,"quantity":1}' >/dev/null
  (curl -s -o /dev/null -w "%{http_code}\n" -XPOST $B/carts/$C/checkout -H 'content-type: application/json' -d '{}' &)
done; wait
# => three 200s and two 409s; product 5 inventory ends at 0
```

**Manual UI:** open `http://localhost:5173` and walk Scenarios B1–B8 above.

---

## 7. Environment used for this report

- PostgreSQL 16 (dedicated `*_test` database created automatically by the harness).
- Backend served via `uvicorn`; frontend via Vite dev server.
- `pytest 8.3` + `pytest-asyncio` + `httpx` ASGI transport.
- Full suite runtime ≈ 9 s.

See [`DECISIONS.md`](./DECISIONS.md) for the design rationale behind every invariant referenced here.
