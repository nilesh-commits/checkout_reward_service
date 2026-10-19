"""Retry safety: a repeated checkout must not create a second order or charge
inventory twice."""
import asyncio

import pytest

from .helpers import cart_with, checkout

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_idempotency_key_returns_same_order(client, make_product):
    pid = await make_product("Hub", 2599, inventory=10)
    cart = await cart_with(client, pid, 2)

    r1 = await checkout(client, cart, idempotency_key="abc-123")
    r2 = await checkout(client, cart, idempotency_key="abc-123")

    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]

    # Inventory charged exactly once (10 - 2).
    products = (await client.get("/products")).json()
    assert next(p for p in products if p["id"] == pid)["inventory"] == 8


async def test_reposting_same_cart_returns_same_order(client, make_product):
    pid = await make_product("Mouse", 4999, inventory=10)
    cart = await cart_with(client, pid, 1)

    r1 = await checkout(client, cart)
    r2 = await checkout(client, cart)  # no key, just the same cart again

    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]

    products = (await client.get("/products")).json()
    assert next(p for p in products if p["id"] == pid)["inventory"] == 9


async def test_concurrent_retries_same_cart_create_one_order(client, make_product):
    pid = await make_product("Monitor", 34900, inventory=10)
    cart = await cart_with(client, pid, 1)

    r1, r2 = await asyncio.gather(
        checkout(client, cart, idempotency_key="race-key"),
        checkout(client, cart, idempotency_key="race-key"),
    )

    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]

    products = (await client.get("/products")).json()
    assert next(p for p in products if p["id"] == pid)["inventory"] == 9
