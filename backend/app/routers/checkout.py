from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..deps import to_order_out
from ..models import Order
from ..schemas import CheckoutIn, OrderOut
from ..services import checkout_service

router = APIRouter(tags=["checkout"])


@router.post("/carts/{cart_id}/checkout", response_model=OrderOut)
async def checkout(
    cart_id: int,
    body: CheckoutIn | None = None,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
):
    """Check out a cart, optionally applying a coupon.

    Safe to retry: pass the same `Idempotency-Key` header (or simply re-POST the
    same cart) and you get the original order back rather than a duplicate.
    The whole operation is one transaction — committed only on success.
    """
    coupon_code = body.coupon_code if body else None
    order = await checkout_service.checkout(
        session, cart_id, coupon_code, idempotency_key
    )
    await session.commit()
    # Re-fetch through a select so the `selectin` items relationship is loaded
    # after the commit (line items were inserted by FK, not via the collection).
    order = (
        await session.execute(select(Order).where(Order.id == order.id))
    ).scalar_one()
    return to_order_out(order)
