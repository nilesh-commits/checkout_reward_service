"""Idempotent product seed.

Runs on startup. Uses INSERT ... ON CONFLICT DO NOTHING keyed on a stable id so
re-running (e.g. container restarts) never duplicates or resets inventory.
Includes one deliberately low-stock product ("Limited Edition Vinyl", 3 units) so
oversell/concurrency behaviour is easy to exercise.
"""
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Product

SEED_PRODUCTS = [
    {"id": 1, "name": "Mechanical Keyboard", "price_cents": 12999, "inventory": 50},
    {"id": 2, "name": "Wireless Mouse", "price_cents": 4999, "inventory": 100},
    {"id": 3, "name": '27" 4K Monitor', "price_cents": 34900, "inventory": 20},
    {"id": 4, "name": "USB-C Hub", "price_cents": 2599, "inventory": 200},
    {"id": 5, "name": "Limited Edition Vinyl", "price_cents": 9900, "inventory": 3},
    {"id": 6, "name": "Desk Mat", "price_cents": 1950, "inventory": 75},
]


async def seed_products(session: AsyncSession) -> None:
    stmt = insert(Product).values(SEED_PRODUCTS).on_conflict_do_nothing(
        index_elements=[Product.id]
    )
    await session.execute(stmt)

    # Keep the identity sequence ahead of the explicitly-inserted ids so future
    # ORM inserts don't collide with the seeded primary keys.
    await session.execute(
        text(
            "SELECT setval(pg_get_serial_sequence('products','id'), "
            "GREATEST((SELECT COALESCE(MAX(id), 1) FROM products), 1))"
        )
    )
    await session.commit()
