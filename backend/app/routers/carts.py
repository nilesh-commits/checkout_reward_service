from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..schemas import AddItemIn, CartOut, UpdateItemIn
from ..services import cart_service

router = APIRouter(tags=["carts"])


@router.post("/carts", response_model=CartOut, status_code=status.HTTP_201_CREATED)
async def create_cart(session: AsyncSession = Depends(get_session)):
    cart = await cart_service.create_cart(session)
    return cart_service.to_cart_out(cart)


@router.get("/carts/{cart_id}", response_model=CartOut)
async def get_cart(cart_id: int, session: AsyncSession = Depends(get_session)):
    cart = await cart_service.get_cart(session, cart_id)
    return cart_service.to_cart_out(cart)


@router.post("/carts/{cart_id}/items", response_model=CartOut)
async def add_item(
    cart_id: int, body: AddItemIn, session: AsyncSession = Depends(get_session)
):
    cart = await cart_service.add_item(session, cart_id, body.product_id, body.quantity)
    return cart_service.to_cart_out(cart)


@router.patch("/carts/{cart_id}/items/{product_id}", response_model=CartOut)
async def update_item(
    cart_id: int,
    product_id: int,
    body: UpdateItemIn,
    session: AsyncSession = Depends(get_session),
):
    cart = await cart_service.update_item(session, cart_id, product_id, body.quantity)
    return cart_service.to_cart_out(cart)


@router.delete("/carts/{cart_id}/items/{product_id}", response_model=CartOut)
async def remove_item(
    cart_id: int, product_id: int, session: AsyncSession = Depends(get_session)
):
    cart = await cart_service.remove_item(session, cart_id, product_id)
    return cart_service.to_cart_out(cart)
