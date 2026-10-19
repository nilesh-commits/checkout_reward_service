# DECISIONS

Design notes for the Checkout & Rewards service. The guiding principle throughout:
**invariants are enforced at the database layer**, because Python-level "check then
act" logic races under concurrency. Approximate time spent: ~5 hours.

---

## System invariants

These are the properties the system must never violate, and where each is enforced:

1. **Inventory is never oversold** (`products.inventory` never < 0).
   Enforced by a guarded conditional UPDATE (`... WHERE inventory >= :qty`) inside the
   checkout transaction, plus a `CHECK (inventory >= 0)` constraint as a backstop.
   (`app/services/checkout_service.py`, `app/models.py`)
2. **A cart produces at most one order.**
   `orders.cart_id` is UNIQUE; checkout locks the cart row and returns the existing
   order if it is already checked out.
3. **A checkout is retry-safe.** Same `Idempotency-Key` or same cart ⇒ the original
   order, never a duplicate. (`orders.idempotency_key` UNIQUE + cart lock.)
4. **A coupon is redeemed at most once, by at most one checkout.**
   A single conditional UPDATE (`active → redeemed`) is the atomic claim; the loser of
   a race affects 0 rows.
5. **A coupon is never consumed by a failed checkout.** The redemption and the order
   live in one transaction; any failure rolls both back.
6. **A coupon is generated at most once per milestone.** `coupons.milestone` UNIQUE +
   `INSERT ... ON CONFLICT DO NOTHING`.
7. **Money is exact.** All amounts are integer cents; the only rounding (percentage
   discount) is half-up via `Decimal`. Totals are clamped to ≥ 0.
8. **Orders are immutable snapshots.** `order_items` store product name and unit price
   as they were at checkout, so later price/catalog changes never rewrite history.
9. **The report is read-only** and reconciles:
   `net == gross − discounts == Σ orders.total_cents`.

---

## Ambiguities found and the semantics chosen

The README deliberately leaves several semantics open. My choices:

- **Price/availability change between add-to-cart and checkout.**
  The cart is a *selection*, not a price lock. Prices are read live when viewing the
  cart and are snapshotted **at checkout**. If stock is insufficient at checkout, the
  checkout fails with `INSUFFICIENT_INVENTORY`; the cart is preserved so the customer
  can adjust. This avoids promising a price we may not honor and keeps the order a true
  record of the transaction.

- **Coupon contention.** If two checkouts race for the same single-use coupon, one
  wins and the **other checkout fails** (`COUPON_INVALID_OR_REDEEMED`) rather than
  silently proceeding without the discount. Rationale: the customer asked for a
  specific price; completing the order at a different price without consent is worse
  than a clear, retryable failure. The client can re-checkout without the coupon.

- **Coupon ↔ order relationship.** A coupon applies to the whole order (one coupon per
  checkout), discounts the subtotal, and is not combinable. The README's reward is a
  percentage, so I model `percent_off` only.

- **Milestone definition.** "Every n-th order" is interpreted as: after order counts
  5, 10, 15, … a coupon becomes available for that milestone. Generation is idempotent
  per milestone; it does not auto-issue on checkout (README says the admin *requests*
  generation).

- **Coupon generation is explicit and lazy.** Reaching a milestone makes a coupon
  *eligible*; the admin endpoint actually creates it. Generating before any milestone
  returns `MILESTONE_NOT_REACHED`; generating twice for the same milestone returns
  `COUPON_ALREADY_GENERATED`.

- **What counts as a "successful order."** Only committed rows in `orders`. A failed /
  rolled-back checkout leaves no order and therefore never advances the milestone.

---

## Material design decisions

### Decision: Enforce invariants with pessimistic row locks + guarded UPDATEs (not app logic, not SERIALIZABLE)

**Context:** Overselling, double-redemption, and duplicate orders are all read-then-write
races. They must hold when requests overlap.

**Options considered:**
1. Application-level checks (read inventory, decide, write) — simple but races.
2. `SERIALIZABLE` isolation with retry-on-serialization-failure.
3. `READ COMMITTED` + `SELECT … FOR UPDATE` on the contended rows + conditional
   UPDATEs whose `WHERE` clause re-asserts the precondition.

**Choice:** Option 3.

**Why:** The contended rows are known and few (the cart, the specific products, the one
coupon), so pessimistic locking is precise and predictable. Products are locked in a
stable order (`ORDER BY id`) to avoid deadlocks. The guarded UPDATEs
(`WHERE inventory >= :qty`, `WHERE status = 'active'`) make the decision and the write a
single atomic statement — the database, not Python, is the arbiter. SERIALIZABLE would
work but forces client-side retry loops and is heavier for a hotspot like a 3-unit
product.

**Consequences:** Correct under concurrency with straightforward code and no retry loop.
The cost is lock contention on hot rows (acceptable, and inherent to the domain). If we
later shard or go multi-region, the locking model still holds within a Postgres primary.

### Decision: Two layers of checkout idempotency (cart identity + Idempotency-Key)

**Context:** A client that times out will retry; the retry must not create a second
order or charge inventory twice.

**Options considered:** Only an `Idempotency-Key` header; only cart-state; both.

**Choice:** Both. `orders.cart_id` UNIQUE guarantees one order per cart regardless of
retries; the optional `Idempotency-Key` header (UNIQUE) short-circuits even before the
cart lock for the classic "lost response" retry.

**Why:** Cart identity is the durable, header-independent guarantee — even a client that
forgets to send a key is safe. The key adds a fast path and supports clients that prefer
the standard idempotency pattern.

**Consequences:** Retried checkouts are safe by construction and return the original
order with 200. A key reused across *different* carts would collide on the UNIQUE
constraint — acceptable, since a key is meant to identify a single logical attempt.

### Decision: Money as integer cents, half-up rounding only on discounts

**Context:** "Calculate money without floating-point rounding errors."

**Options considered:** floats (rejected outright), `Decimal` everywhere, integer minor
units.

**Choice:** Integer cents in the DB (`BIGINT`), in services, and in the API
(`*_cents` + a `*_display` string). The single unavoidable rounding — a percentage
discount — uses `Decimal` with `ROUND_HALF_UP`, then clamps the discount to the subtotal.

**Why:** Integer arithmetic is exact and trivially auditable; storing the result of the
one rounding operation means the order's totals are internally consistent forever. Clamp
guarantees totals never go negative.

**Consequences:** No float ever touches money. Multi-currency / sub-cent pricing would
need a currency+scale column later (deferred).

### Decision: Orders snapshot line items

**Context:** "An order must retain enough information… even if product data later
changes."

**Choice:** `order_items` copy `product_name` and `unit_price_cents` at checkout; the
order stores `subtotal/discount/total`. The report aggregates from these snapshots, not
from live products.

**Why:** Products are mutable; orders are historical fact. Deriving an old order's total
from today's prices would be wrong.

**Consequences:** A product rename/reprice/deletion never corrupts past orders or the
revenue report. Slight duplication of product data into order rows (intended).

### Decision: `create_all` + idempotent seed instead of Alembic migrations

**Context:** The service needs a schema and seed data, within a 4–6h timebox.

**Options considered:** Alembic migrations; raw SQL init; `metadata.create_all` + an
idempotent seed on startup.

**Choice:** `create_all` + `INSERT … ON CONFLICT DO NOTHING` seed.

**Why:** Fastest path to a reproducible, clone-and-run environment; the schema is the
single source of truth in `models.py`. Alembic is the right production answer but is
pure overhead for a greenfield evaluation.

**Consequences:** Zero-friction startup; **but** no migration history, so schema changes
in production would require introducing Alembic. Explicitly deferred (below).

### Decision: Explicit admin boundary via a shared token, no real auth

**Context:** README says auth isn't required but admin operations must be identified.

**Choice:** `/admin/*` operations require an `X-Admin-Token` header matching an env
value; everything else is public.

**Why:** Makes the admin boundary explicit and testable without building authn/authz
that the brief excludes.

**Consequences:** The boundary is clear and the report/coupon endpoints are gated. Real
deployments must replace this with proper authentication/authorization.

---

## Transaction, concurrency, and idempotency strategy (summary)

- **Isolation:** READ COMMITTED (Postgres default).
- **Checkout** runs as one transaction, committed by the router only on success:
  1. `Idempotency-Key` fast path → existing order.
  2. `SELECT … FOR UPDATE` the cart (serializes same-cart checkouts); if already
     checked out, return its order.
  3. `SELECT … FOR UPDATE` products `ORDER BY id` (deadlock-free lock ordering).
  4. Snapshot prices; compute subtotal.
  5. Coupon claim: `UPDATE coupons SET status='redeemed' … WHERE status='active'`
     (0 rows ⇒ fail).
  6. Inventory: `UPDATE products SET inventory = inventory - q WHERE inventory >= q`
     (0 rows ⇒ fail).
  7. Insert order + snapshot items; mark cart checked out.
  Any raise ⇒ rollback ⇒ coupon and inventory restored atomically.
- **Coupon generation** uses `INSERT … ON CONFLICT (milestone) DO NOTHING` so concurrent
  admin calls can't double-issue.
- **Tests** exercise this with `asyncio.gather` over real concurrent HTTP requests, each
  on its own DB connection, contending on the same rows.

---

## Error model

All errors return `{ "error": { "code", "message", "details" } }` with a stable machine
`code` so clients branch on failure mode without string-matching. Status mapping:

| Code | HTTP | Meaning |
|------|------|---------|
| `VALIDATION_ERROR` | 422 | Malformed request / bad quantity |
| `CART_EMPTY` | 400 | Checkout attempted on an empty cart |
| `CART_NOT_FOUND` / `PRODUCT_NOT_FOUND` / `ORDER_NOT_FOUND` / `CART_ITEM_NOT_FOUND` | 404 | Missing resource |
| `INSUFFICIENT_INVENTORY` | 409 | Not enough stock (includes offending product in `details`) |
| `COUPON_INVALID_OR_REDEEMED` | 409 | Unknown or already-used coupon |
| `MILESTONE_NOT_REACHED` | 409 | No eligible unrewarded milestone |
| `COUPON_ALREADY_GENERATED` | 409 | Milestone already rewarded |
| `UNAUTHORIZED` | 401 | Missing/wrong admin token |

A checked-out cart being checked out again is deliberately **not** an error — it returns
the existing order (idempotency).

---

## Implemented vs. intentionally deferred

**Implemented:** products + inventory, carts (CRUD + validation), checkout with coupon,
idempotent retries, concurrent-safe inventory and coupon handling, order snapshots,
admin coupon generation, read-only reconciling report, structured errors, Docker Compose
(Postgres + FastAPI + React), focused invariant tests, OpenAPI docs at `/docs`.

**Deferred (and why):**
- **Alembic migrations** — used `create_all` for timebox; needed before any production schema change.
- **Real authn/authz** — out of scope per README; admin token is a placeholder.
- **Real payment** — checkout *is* the payment success boundary; a payment step would slot in before inventory commit as its own idempotent call.
- **Cart TTL / abandoned-cart cleanup, pagination, rate limiting.**
- **Partial fulfillment / backorders** — current semantics are all-or-nothing.
- **Coupon expiry, per-customer coupons, stacking.**
- **Observability** (structured logs/metrics/tracing) and a CI pipeline.

---

## How the design evolves for multiple instances and production scale

The design is already **stateless at the app tier** — all shared state lives in Postgres
and all invariants are enforced there — so it scales horizontally *as is*:

- **Multiple app instances** behind a load balancer: safe today. The row locks and
  conditional UPDATEs coordinate across instances because coordination happens in the
  database, not in process memory. (This is the key reason no in-memory lock or
  singleton was used.)
- **Database scale:** reads (the report, product listing) go to read replicas; the
  checkout path stays on the primary. Hot-row contention (a popular limited product) is
  intrinsic; mitigate with short transactions (already the case) and, if needed, inventory
  sharding/reservation counters.
- **Idempotency at scale:** the `Idempotency-Key` table would get a TTL/cleanup job.
- **Payments:** introduce a real PSP with its own idempotency key; make checkout a saga
  (reserve inventory → charge → confirm) with compensation on failure.
- **Reporting at volume:** replace on-the-fly aggregation with incrementally-maintained
  rollups (materialized views or an event/outbox pipeline) to keep the report O(1).
- **Migrations:** Alembic in CI; expand-contract for zero-downtime schema changes.

---

## How AI tools were used

I used an AI coding assistant (Claude) to scaffold the project, draft the service layer,
the React UI, and this document, then reviewed and corrected every file. Concrete
examples where I corrected or redirected the generated output:

1. **Pydantic serialization bug (corrected).** The first draft of `schemas.py` exposed
   money display strings as plain `@property` methods. In Pydantic v2 those are **not**
   serialized into responses, so the API would have silently omitted every `*_display`
   field. I replaced them with `@computed_field` so they actually appear in the JSON.

2. **Docker/test mismatch (corrected).** An early `backend/.dockerignore` excluded the
   `tests/` directory, which would have broken the documented
   `docker compose run --rm backend pytest` verification step. I removed that exclusion.

3. **Event-loop/pool trap in tests (redirected).** The naive test setup would have created
   the async engine on one event loop and run tests on per-test loops, causing asyncpg
   "attached to a different loop" failures. I redirected the harness to a single
   session-scoped loop (`loop_scope="session"`) and real concurrent requests via
   `ASGITransport` + `asyncio.gather`, which is what makes the concurrency tests
   trustworthy rather than theatrical.

4. **Seed hygiene (corrected).** The generated seed left a dead query and an inline
   `__import__` call; I rewrote it to a clean `ON CONFLICT DO NOTHING` insert plus a
   `setval` to keep the identity sequence ahead of the seeded ids.

I own every line submitted and can explain where each invariant is enforced and predict
behavior under concurrent/repeated requests.

---

## What I would examine first given another two hours

1. **A property-based / stress test** firing hundreds of randomized concurrent carts at a
   small inventory and asserting `Σ sold ≤ initial stock` and report reconciliation — to
   hunt for any invariant gap the targeted tests miss.
2. **A Postgres advisory-lock or `SKIP LOCKED` experiment** for the hottest product to
   measure contention vs. the current `FOR UPDATE` approach under load.
3. **Idempotency-key edge cases**: same key across different carts, and concurrent first
   requests with the same key (currently handled by the cart lock + UNIQUE, but I'd add
   an explicit test and a cleaner 409 for key/cart mismatch).
4. **Introduce Alembic** and a minimal CI workflow running the test suite against a
   throwaway Postgres.
