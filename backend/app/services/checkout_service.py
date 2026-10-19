"""Checkout — the correctness-critical path.

Everything here runs inside ONE database transaction. The ordering and the use of
row locks / guarded UPDATEs is deliberate; see DECISIONS.md. The transaction is
owned by the caller's session and committed by the router on success, so any
exception rolls the whole thing back — undoing coupon redemption and inventory
decrements atomically.

Concurrency strategy (READ COMMITTED + pessimistic locks):
  1. Idempotency-Key short-circuit (network retry).
  2. Lock the cart row FOR UPDATE; if already checked out, return the existing
     order (cart-level idempotency — a retry never creates a second order).
  3. Lock all involved product rows FOR UPDATE, ordered by id (deadlock-free).
  4. Snapshot prices, compute money in cents.
  5. Claim the coupon with a conditional UPDATE (active -> redeemed); loser of a
     race gets 0 rows affected.
  6. Decrement inventory with a guarded UPDATE (inventory >= qty); loser gets 0.
  7. Persist order + snapshot line items; mark cart checked_out.
"""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..errors import (
    CartEmpty,
    CartNotFound,
    CouponInvalidOrRedeemed,
    InsufficientInventory,
)
from ..models import (
    Cart,
    CartItem,
    CartStatus,
    Coupon,
    CouponStatus,
    Order,
    OrderItem,
    Product,
)
from ..money import discount_cents

settings = get_settings()


async def _existing_order_for_cart(session: AsyncSession, cart_id: int) -> Order | None:
    res = await session.execute(select(Order).where(Order.cart_id == cart_id))
    return res.scalar_one_or_none()


async def _order_for_idempotency_key(
    session: AsyncSession, key: str
) -> Order | None:
    res = await session.execute(
        select(Order).where(Order.idempotency_key == key)
    )
    return res.scalar_one_or_none()


async def checkout(
    session: AsyncSession,
    cart_id: int,
    coupon_code: str | None,
    idempotency_key: str | None,
) -> Order:
    # (1) Network-retry idempotency: same key already produced an order.
    if idempotency_key:
        existing = await _order_for_idempotency_key(session, idempotency_key)
        if existing is not None:
            return existing

    # (2) Lock the cart. FOR UPDATE serialises concurrent checkouts of the SAME cart.
    res = await session.execute(
        select(Cart).where(Cart.id == cart_id).with_for_update()
    )
    cart = res.scalar_one_or_none()
    if cart is None:
        raise CartNotFound()

    if cart.status == CartStatus.checked_out:
        # Cart-level idempotency: the order already exists; return it instead of erroring.
        existing = await _existing_order_for_cart(session, cart_id)
        if existing is not None:
            return existing
        raise CartNotFound("Cart is checked out but has no order")

    # Load items.
    res = await session.execute(
        select(CartItem).where(CartItem.cart_id == cart_id)
    )
    items = list(res.scalars().all())
    if not items:
        raise CartEmpty()

    # (3) Lock product rows in a stable order (by id) to avoid deadlocks between
    # concurrent checkouts touching overlapping products.
    product_ids = sorted(i.product_id for i in items)
    res = await session.execute(
        select(Product)
        .where(Product.id.in_(product_ids))
        .order_by(Product.id)
        .with_for_update()
    )
    products = {p.id: p for p in res.scalars().all()}

    # (4) Snapshot prices and compute subtotal in cents.
    subtotal = 0
    snapshots: list[tuple[Product, int]] = []
    for item in items:
        product = products.get(item.product_id)
        if product is None:
            raise InsufficientInventory(
                f"Product {item.product_id} is no longer available"
            )
        subtotal += product.price_cents * item.quantity
        snapshots.append((product, item.quantity))

    # Build the order first so we can reference its id from the coupon redemption.
    order = Order(
        cart_id=cart_id,
        idempotency_key=idempotency_key,
        subtotal_cents=subtotal,
        discount_cents=0,
        total_cents=subtotal,
        coupon_code=None,
    )
    session.add(order)
    await session.flush()  # assigns order.id without committing

    # (5) Coupon: conditional claim. Winner flips active -> redeemed in one UPDATE.
    discount = 0
    if coupon_code:
        res = await session.execute(
            update(Coupon)
            .where(Coupon.code == coupon_code, Coupon.status == CouponStatus.active)
            .values(status=CouponStatus.redeemed, redeemed_order_id=order.id)
            .returning(Coupon.percent_off)
        )
        row = res.first()
        if row is None:
            # Either the code doesn't exist or another checkout already redeemed it.
            raise CouponInvalidOrRedeemed()
        percent_off = row[0]
        discount = discount_cents(subtotal, percent_off)
        order.coupon_code = coupon_code
        order.discount_cents = discount
        order.total_cents = max(0, subtotal - discount)

    # (6) Decrement inventory with a guarded UPDATE. rowcount 0 => oversell attempt.
    for product, qty in snapshots:
        res = await session.execute(
            update(Product)
            .where(Product.id == product.id, Product.inventory >= qty)
            .values(inventory=Product.inventory - qty)
        )
        if res.rowcount != 1:
            raise InsufficientInventory(
                details={"product_id": product.id, "requested": qty}
            )

    # (7) Snapshot line items and close the cart.
    for product, qty in snapshots:
        session.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name=product.name,
                unit_price_cents=product.price_cents,
                quantity=qty,
            )
        )
    cart.status = CartStatus.checked_out

    await session.flush()
    return order
