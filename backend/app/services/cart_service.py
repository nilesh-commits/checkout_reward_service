"""Cart operations and cart-view assembly.

Validation lives here so invalid products/quantities can never silently enter a
cart (README requirement). Cart views compute prices/totals from *current* product
prices — the snapshot only happens at checkout (documented in DECISIONS.md).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import CartItemNotFound, CartNotFound, ProductNotFound, ValidationError
from ..models import Cart, CartItem, CartStatus, Product
from ..schemas import CartItemOut, CartOut


async def create_cart(session: AsyncSession) -> Cart:
    cart = Cart(status=CartStatus.open)
    session.add(cart)
    await session.commit()
    await session.refresh(cart)
    return cart


async def _get_open_cart(session: AsyncSession, cart_id: int) -> Cart:
    cart = (
        await session.execute(select(Cart).where(Cart.id == cart_id))
    ).scalar_one_or_none()
    if cart is None:
        raise CartNotFound()
    if cart.status != CartStatus.open:
        raise ValidationError("Cart is already checked out and cannot be modified")
    return cart


async def add_item(
    session: AsyncSession, cart_id: int, product_id: int, quantity: int
) -> Cart:
    await _get_open_cart(session, cart_id)

    product = (
        await session.execute(select(Product).where(Product.id == product_id))
    ).scalar_one_or_none()
    if product is None:
        raise ProductNotFound(details={"product_id": product_id})

    existing = (
        await session.execute(
            select(CartItem).where(
                CartItem.cart_id == cart_id, CartItem.product_id == product_id
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        session.add(CartItem(cart_id=cart_id, product_id=product_id, quantity=quantity))
    else:
        existing.quantity += quantity

    await session.commit()
    return await get_cart(session, cart_id, as_model=True)


async def update_item(
    session: AsyncSession, cart_id: int, product_id: int, quantity: int
) -> Cart:
    await _get_open_cart(session, cart_id)
    item = (
        await session.execute(
            select(CartItem).where(
                CartItem.cart_id == cart_id, CartItem.product_id == product_id
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise CartItemNotFound(details={"product_id": product_id})
    item.quantity = quantity
    await session.commit()
    return await get_cart(session, cart_id, as_model=True)


async def remove_item(session: AsyncSession, cart_id: int, product_id: int) -> Cart:
    await _get_open_cart(session, cart_id)
    item = (
        await session.execute(
            select(CartItem).where(
                CartItem.cart_id == cart_id, CartItem.product_id == product_id
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise CartItemNotFound(details={"product_id": product_id})
    await session.delete(item)
    await session.commit()
    return await get_cart(session, cart_id, as_model=True)


async def get_cart(session: AsyncSession, cart_id: int, as_model: bool = True) -> Cart:
    cart = (
        await session.execute(select(Cart).where(Cart.id == cart_id))
    ).scalar_one_or_none()
    if cart is None:
        raise CartNotFound()
    return cart


def to_cart_out(cart: Cart) -> CartOut:
    """Build the API view from a loaded cart (items eager-loaded via selectin)."""
    item_views: list[CartItemOut] = []
    subtotal = 0
    for item in sorted(cart.items, key=lambda i: i.product_id):
        unit = item.product.price_cents
        line = unit * item.quantity
        subtotal += line
        item_views.append(
            CartItemOut(
                product_id=item.product_id,
                name=item.product.name,
                unit_price_cents=unit,
                quantity=item.quantity,
                line_total_cents=line,
            )
        )
    return CartOut(
        id=cart.id,
        status=cart.status.value,
        items=item_views,
        subtotal_cents=subtotal,
    )
