"""Small HTTP helpers shared across tests."""
from __future__ import annotations

import httpx


async def new_cart(client: httpx.AsyncClient) -> int:
    r = await client.post("/carts")
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def add_item(
    client: httpx.AsyncClient, cart_id: int, product_id: int, quantity: int
) -> httpx.Response:
    return await client.post(
        f"/carts/{cart_id}/items",
        json={"product_id": product_id, "quantity": quantity},
    )


async def cart_with(
    client: httpx.AsyncClient, product_id: int, quantity: int
) -> int:
    cart_id = await new_cart(client)
    r = await add_item(client, cart_id, product_id, quantity)
    assert r.status_code == 200, r.text
    return cart_id


async def checkout(
    client: httpx.AsyncClient,
    cart_id: int,
    coupon_code: str | None = None,
    idempotency_key: str | None = None,
) -> httpx.Response:
    headers = {}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    body = {"coupon_code": coupon_code} if coupon_code is not None else {}
    return await client.post(
        f"/carts/{cart_id}/checkout", json=body, headers=headers
    )
