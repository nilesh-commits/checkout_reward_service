"""The admin report must reconcile and must not mutate state on repeated calls."""
import pytest
from sqlalchemy import select

from app.models import Coupon, CouponStatus

from .helpers import cart_with, checkout
from .conftest import ADMIN_HEADERS

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_report_reconciles_and_is_read_only(client, session, make_product):
    pid_a = await make_product("Widget A", 1000, inventory=100)
    pid_b = await make_product("Widget B", 2500, inventory=100)

    # One coupon, redeemed on the second order.
    session.add(Coupon(code="SAVE-RPT", percent_off=10, status=CouponStatus.active))
    await session.commit()

    # Order 1: 2x A + 1x B, no coupon. subtotal = 2000 + 2500 = 4500
    c1 = await cart_with(client, pid_a, 2)
    await client.post(
        f"/carts/{c1}/items", json={"product_id": pid_b, "quantity": 1}
    )
    o1 = (await checkout(client, c1)).json()

    # Order 2: 3x A, 10% coupon. subtotal = 3000, discount 300, total 2700
    c2 = await cart_with(client, pid_a, 3)
    o2 = (await checkout(client, c2, coupon_code="SAVE-RPT")).json()

    r1 = (await client.get("/admin/report", headers=ADMIN_HEADERS)).json()

    assert r1["total_orders"] == 2
    assert r1["gross_revenue_cents"] == 4500 + 3000
    assert r1["total_discounts_cents"] == 300
    assert r1["net_revenue_cents"] == r1["gross_revenue_cents"] - r1["total_discounts_cents"]
    assert r1["net_revenue_cents"] == o1["total_cents"] + o2["total_cents"]

    # Purchased quantities: A = 2 + 3 = 5, B = 1
    sold = {s["product_id"]: s["quantity"] for s in r1["purchased_quantity_by_product"]}
    assert sold[pid_a] == 5
    assert sold[pid_b] == 1

    assert r1["coupons_generated"] == 1
    assert r1["coupons_redeemed"] == 1
    assert r1["coupons_available"] == 0

    # Calling again yields identical numbers and does not mutate anything.
    r2 = (await client.get("/admin/report", headers=ADMIN_HEADERS)).json()
    assert r1 == r2

    coupon = (
        await session.execute(select(Coupon).where(Coupon.code == "SAVE-RPT"))
    ).scalar_one()
    await session.refresh(coupon)
    assert coupon.status == CouponStatus.redeemed
