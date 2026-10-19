"""Invalid products/quantities must never silently enter a cart; empty carts and
checked-out carts behave coherently."""
import pytest

from .helpers import add_item, cart_with, checkout, new_cart

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_unknown_product_rejected(client):
    cart = await new_cart(client)
    r = await add_item(client, cart, product_id=99999, quantity=1)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


async def test_non_positive_quantity_rejected(client, make_product):
    pid = await make_product("Thing", 1000, inventory=5)
    cart = await new_cart(client)
    r = await add_item(client, cart, product_id=pid, quantity=0)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_checkout_empty_cart_rejected(client):
    cart = await new_cart(client)
    r = await checkout(client, cart)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "CART_EMPTY"


async def test_cannot_modify_checked_out_cart(client, make_product):
    pid = await make_product("Thing", 1000, inventory=5)
    cart = await cart_with(client, pid, 1)
    assert (await checkout(client, cart)).status_code == 200

    r = await add_item(client, cart, product_id=pid, quantity=1)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
