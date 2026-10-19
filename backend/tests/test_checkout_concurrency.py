"""The required non-happy-path test: concurrent checkouts must not oversell."""
import asyncio

import pytest

from .helpers import cart_with, checkout

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_concurrent_checkouts_do_not_oversell(client, make_product):
    # 3 units in stock, 5 shoppers each trying to buy 1, all at once.
    pid = await make_product("Limited Vinyl", 9900, inventory=3)

    carts = [await cart_with(client, pid, 1) for _ in range(5)]
    responses = await asyncio.gather(*(checkout(client, c) for c in carts))

    statuses = sorted(r.status_code for r in responses)
    successes = [r for r in responses if r.status_code == 200]
    failures = [r for r in responses if r.status_code != 200]

    # Exactly 3 succeed, 2 fail — never 4+ (which would be an oversell).
    assert len(successes) == 3, statuses
    assert len(failures) == 2, statuses
    for r in failures:
        assert r.json()["error"]["code"] == "INSUFFICIENT_INVENTORY"

    # Inventory lands at exactly 0 and was never allowed to go negative.
    products = (await client.get("/products")).json()
    vinyl = next(p for p in products if p["id"] == pid)
    assert vinyl["inventory"] == 0
