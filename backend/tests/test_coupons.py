"""Coupon invariants: redeemed once, never lost by a failed checkout, and
generated once per milestone."""
import asyncio

import pytest
from sqlalchemy import select

from app.models import Coupon, CouponStatus

from .helpers import cart_with, checkout
from .conftest import ADMIN_HEADERS

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _insert_coupon(session, code="SAVE-TEST", percent=10) -> str:
    session.add(Coupon(code=code, percent_off=percent, status=CouponStatus.active))
    await session.commit()
    return code


async def _coupon_status(session, code: str) -> str:
    row = (
        await session.execute(select(Coupon).where(Coupon.code == code))
    ).scalar_one()
    await session.refresh(row)
    return row.status.value


async def test_coupon_redeemed_by_only_one_of_two_concurrent_checkouts(
    client, session, make_product
):
    code = await _insert_coupon(session)
    pid = await make_product("Keyboard", 10000, inventory=10)

    c1 = await cart_with(client, pid, 1)
    c2 = await cart_with(client, pid, 1)

    r1, r2 = await asyncio.gather(
        checkout(client, c1, coupon_code=code),
        checkout(client, c2, coupon_code=code),
    )

    # Exactly one wins the coupon (200); the other's checkout fails cleanly (409).
    assert sorted([r1.status_code, r2.status_code]) == [200, 409]

    winner = r1 if r1.status_code == 200 else r2
    loser = r2 if r1.status_code == 200 else r1
    assert winner.json()["discount_cents"] == 1000  # 10% of 10000
    assert loser.json()["error"]["code"] == "COUPON_INVALID_OR_REDEEMED"

    assert await _coupon_status(session, code) == "redeemed"


async def test_failed_checkout_does_not_consume_coupon(client, session, make_product):
    code = await _insert_coupon(session, code="SAVE-KEEP")
    pid = await make_product("Rare Item", 5000, inventory=1)

    # Ask for 2 but only 1 in stock -> checkout fails AFTER the coupon claim step,
    # so the rollback must restore the coupon to active.
    cart = await cart_with(client, pid, 2)
    r = await checkout(client, cart, coupon_code=code)

    assert r.status_code == 409
    assert r.json()["error"]["code"] == "INSUFFICIENT_INVENTORY"
    assert await _coupon_status(session, code) == "active"


async def test_milestone_generation_is_once_per_milestone(client, make_product):
    pid = await make_product("Cheap Thing", 1000, inventory=100)

    async def place_order():
        cart = await cart_with(client, pid, 1)
        r = await checkout(client, cart)
        assert r.status_code == 200, r.text

    # 4 orders: milestone (n=5) not reached yet.
    for _ in range(4):
        await place_order()
    r = await client.post("/admin/coupons/generate", headers=ADMIN_HEADERS)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "MILESTONE_NOT_REACHED"

    # 5th order: milestone 5 now eligible.
    await place_order()
    r = await client.post("/admin/coupons/generate", headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    assert r.json()["milestone"] == 5
    assert r.json()["percent_off"] == 10

    # Second generation for the same milestone is rejected.
    r = await client.post("/admin/coupons/generate", headers=ADMIN_HEADERS)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "COUPON_ALREADY_GENERATED"


async def test_admin_requires_token(client):
    r = await client.post("/admin/coupons/generate")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"
