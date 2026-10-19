"""Shared FastAPI dependencies and small serialization helpers."""
from __future__ import annotations

from fastapi import Header

from .config import get_settings
from .errors import Unauthorized
from .models import Order
from .schemas import OrderItemOut, OrderOut

settings = get_settings()


async def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """Marks an operation as administrative.

    Real authn/authz is intentionally out of scope (README). This simply checks a
    shared token so the admin boundary is explicit and testable.
    """
    if x_admin_token != settings.admin_token:
        raise Unauthorized()


def to_order_out(order: Order) -> OrderOut:
    return OrderOut(
        id=order.id,
        cart_id=order.cart_id,
        items=[
            OrderItemOut(
                product_id=i.product_id,
                product_name=i.product_name,
                unit_price_cents=i.unit_price_cents,
                quantity=i.quantity,
                line_total_cents=i.unit_price_cents * i.quantity,
            )
            for i in sorted(order.items, key=lambda i: i.product_id)
        ],
        subtotal_cents=order.subtotal_cents,
        discount_cents=order.discount_cents,
        total_cents=order.total_cents,
        coupon_code=order.coupon_code,
        created_at=order.created_at,
    )
