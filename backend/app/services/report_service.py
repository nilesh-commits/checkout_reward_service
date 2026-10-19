"""Admin reporting — strictly read-only aggregation.

Every figure is derived with SELECTs over orders / order_items / coupons, so
repeated calls never mutate state and the report always reconciles with the
underlying data:

    net_revenue == gross_revenue - total_discounts == sum(orders.total_cents)
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Coupon, CouponStatus, Order, OrderItem
from ..schemas import ProductSoldOut, ReportOut


async def build_report(session: AsyncSession) -> ReportOut:
    total_orders = (
        await session.execute(select(func.count()).select_from(Order))
    ).scalar_one()

    gross = (
        await session.execute(select(func.coalesce(func.sum(Order.subtotal_cents), 0)))
    ).scalar_one()
    discounts = (
        await session.execute(select(func.coalesce(func.sum(Order.discount_cents), 0)))
    ).scalar_one()
    net = (
        await session.execute(select(func.coalesce(func.sum(Order.total_cents), 0)))
    ).scalar_one()

    sold_rows = (
        await session.execute(
            select(
                OrderItem.product_id,
                func.max(OrderItem.product_name),
                func.sum(OrderItem.quantity),
            )
            .group_by(OrderItem.product_id)
            .order_by(OrderItem.product_id)
        )
    ).all()
    purchased = [
        ProductSoldOut(product_id=pid, product_name=name, quantity=qty)
        for (pid, name, qty) in sold_rows
    ]

    coupons_generated = (
        await session.execute(select(func.count()).select_from(Coupon))
    ).scalar_one()
    coupons_redeemed = (
        await session.execute(
            select(func.count())
            .select_from(Coupon)
            .where(Coupon.status == CouponStatus.redeemed)
        )
    ).scalar_one()
    coupons_available = coupons_generated - coupons_redeemed

    return ReportOut(
        total_orders=total_orders,
        purchased_quantity_by_product=purchased,
        gross_revenue_cents=gross,
        total_discounts_cents=discounts,
        net_revenue_cents=net,
        coupons_generated=coupons_generated,
        coupons_available=coupons_available,
        coupons_redeemed=coupons_redeemed,
    )
