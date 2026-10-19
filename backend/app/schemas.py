"""Pydantic request/response models (the API contract).

Monetary fields are exposed as integer `*_cents` plus a formatted display string
(via `computed_field`), so clients never have to parse money out of a float.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from .money import format_cents


# ---------- Products ----------
class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    price_cents: int
    inventory: int

    @computed_field
    @property
    def price_display(self) -> str:
        return format_cents(self.price_cents)


# ---------- Carts ----------
class AddItemIn(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=1000)


class UpdateItemIn(BaseModel):
    quantity: int = Field(gt=0, le=1000)


class CartItemOut(BaseModel):
    product_id: int
    name: str
    unit_price_cents: int
    quantity: int
    line_total_cents: int

    @computed_field
    @property
    def unit_price_display(self) -> str:
        return format_cents(self.unit_price_cents)

    @computed_field
    @property
    def line_total_display(self) -> str:
        return format_cents(self.line_total_cents)


class CartOut(BaseModel):
    id: int
    status: str
    items: list[CartItemOut]
    subtotal_cents: int

    @computed_field
    @property
    def subtotal_display(self) -> str:
        return format_cents(self.subtotal_cents)


# ---------- Checkout / Orders ----------
class CheckoutIn(BaseModel):
    coupon_code: str | None = None


class OrderItemOut(BaseModel):
    product_id: int
    product_name: str
    unit_price_cents: int
    quantity: int
    line_total_cents: int

    @computed_field
    @property
    def line_total_display(self) -> str:
        return format_cents(self.line_total_cents)


class OrderOut(BaseModel):
    id: int
    cart_id: int
    items: list[OrderItemOut]
    subtotal_cents: int
    discount_cents: int
    total_cents: int
    coupon_code: str | None
    created_at: datetime

    @computed_field
    @property
    def subtotal_display(self) -> str:
        return format_cents(self.subtotal_cents)

    @computed_field
    @property
    def discount_display(self) -> str:
        return format_cents(self.discount_cents)

    @computed_field
    @property
    def total_display(self) -> str:
        return format_cents(self.total_cents)


# ---------- Coupons / Admin ----------
class CouponOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    percent_off: int
    milestone: int | None
    status: str
    redeemed_order_id: int | None


class ProductSoldOut(BaseModel):
    product_id: int
    product_name: str
    quantity: int


class ReportOut(BaseModel):
    total_orders: int
    purchased_quantity_by_product: list[ProductSoldOut]
    gross_revenue_cents: int
    total_discounts_cents: int
    net_revenue_cents: int
    coupons_generated: int
    coupons_available: int
    coupons_redeemed: int

    @computed_field
    @property
    def gross_revenue_display(self) -> str:
        return format_cents(self.gross_revenue_cents)

    @computed_field
    @property
    def net_revenue_display(self) -> str:
        return format_cents(self.net_revenue_cents)
