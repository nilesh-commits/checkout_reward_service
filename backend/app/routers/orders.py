from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..deps import to_order_out
from ..errors import OrderNotFound
from ..models import Order
from ..schemas import OrderOut

router = APIRouter(tags=["orders"])


@router.get("/orders/{order_id}", response_model=OrderOut)
async def get_order(order_id: int, session: AsyncSession = Depends(get_session)):
    order = (
        await session.execute(select(Order).where(Order.id == order_id))
    ).scalar_one_or_none()
    if order is None:
        raise OrderNotFound()
    return to_order_out(order)
