"""SQLAlchemy ORM models.

Database-level constraints are the backbone of the invariants:
  * `products.inventory >= 0` CHECK + guarded UPDATE  -> never oversell
  * `orders.cart_id` UNIQUE                           -> one order per cart
  * `orders.idempotency_key` UNIQUE                   -> retry-safe checkout
  * `coupons.code` UNIQUE                             -> coupon identity
  * `coupons.milestone` UNIQUE                        -> one coupon per milestone
  * `cart_items (cart_id, product_id)` UNIQUE         -> no duplicate lines

Enforcing these in the DB (not Python) is what makes them hold under concurrency.
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class CartStatus(str, enum.Enum):
    open = "open"
    checked_out = "checked_out"


class CouponStatus(str, enum.Enum):
    active = "active"
    redeemed = "redeemed"


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (CheckConstraint("inventory >= 0", name="inventory_non_negative"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    inventory: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Cart(Base):
    __tablename__ = "carts"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[CartStatus] = mapped_column(
        Enum(CartStatus, name="cart_status"),
        nullable=False,
        default=CartStatus.open,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    items: Mapped[list[CartItem]] = relationship(
        back_populates="cart", cascade="all, delete-orphan", lazy="selectin"
    )


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("cart_id", "product_id", name="uq_cart_product"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cart_id: Mapped[int] = mapped_column(ForeignKey("carts.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    cart: Mapped[Cart] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(lazy="joined")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("cart_id", name="uq_order_cart"),
        UniqueConstraint("idempotency_key", name="uq_order_idempotency_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cart_id: Mapped[int] = mapped_column(ForeignKey("carts.id"), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)

    subtotal_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    coupon_code: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )


class OrderItem(Base):
    """Immutable snapshot of a purchased line (name + unit price at purchase time)."""

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    order: Mapped[Order] = relationship(back_populates="items")


class Coupon(Base):
    __tablename__ = "coupons"
    __table_args__ = (
        UniqueConstraint("code", name="uq_coupon_code"),
        UniqueConstraint("milestone", name="uq_coupon_milestone"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    percent_off: Mapped[int] = mapped_column(Integer, nullable=False)
    # The order count this coupon rewards (e.g. 5, 10, ...). NULL would allow
    # manually-issued coupons; milestone coupons always set it.
    milestone: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[CouponStatus] = mapped_column(
        Enum(CouponStatus, name="coupon_status"),
        nullable=False,
        default=CouponStatus.active,
    )
    redeemed_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
