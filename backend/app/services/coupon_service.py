"""Coupon generation (administrative).

A coupon becomes available after every n-th successfully placed order. Generation
is explicit (admin-triggered) and must be idempotent per milestone: calling it
twice for the same milestone yields the same single coupon, never two.

We compute the current eligible milestone as floor(order_count / n) * n and insert
a coupon carrying that `milestone`. The UNIQUE(milestone) constraint + INSERT ...
ON CONFLICT DO NOTHING makes "one coupon per milestone" hold even under concurrent
generation requests.
"""
from __future__ import annotations

import secrets

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..errors import CouponAlreadyGenerated, MilestoneNotReached
from ..models import Coupon, CouponStatus, Order

settings = get_settings()


def _new_code() -> str:
    return "SAVE-" + secrets.token_hex(4).upper()


async def generate_coupon(session: AsyncSession) -> Coupon:
    n = settings.coupon_order_interval

    order_count = (
        await session.execute(select(func.count()).select_from(Order))
    ).scalar_one()

    milestone = (order_count // n) * n
    if milestone <= 0:
        raise MilestoneNotReached(
            details={"orders": order_count, "interval": n}
        )

    # Insert-or-nothing on the milestone. If a coupon for this milestone already
    # exists, 0 rows are returned and we surface COUPON_ALREADY_GENERATED.
    stmt = (
        insert(Coupon)
        .values(
            code=_new_code(),
            percent_off=settings.coupon_percent,
            milestone=milestone,
            status=CouponStatus.active,
        )
        .on_conflict_do_nothing(index_elements=[Coupon.milestone])
        .returning(Coupon.id)
    )
    res = await session.execute(stmt)
    inserted_id = res.scalar_one_or_none()

    if inserted_id is None:
        await session.rollback()
        raise CouponAlreadyGenerated(details={"milestone": milestone})

    await session.commit()
    coupon = (
        await session.execute(select(Coupon).where(Coupon.id == inserted_id))
    ).scalar_one()
    return coupon
