"""Test harness.

Design choices for trustworthy concurrency tests:

* A dedicated test database (`<db>_test`) is created if absent, so running the
  suite never clobbers the app's seeded data.
* The whole suite runs on ONE event loop (`loop_scope="session"`), so the single
  async engine / asyncpg pool is bound to one loop — the standard way to avoid
  "attached to a different loop" errors.
* Requests go through the real ASGI app via httpx's ASGITransport. Each request
  gets its own DB session/connection from the pool, so `asyncio.gather` produces
  genuinely concurrent transactions that contend on the same Postgres row locks —
  exactly what we want to test.
"""
import asyncio
import os
from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest
import pytest_asyncio

# --- Point the app at a dedicated test database BEFORE importing it ----------
_BASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://uniblox:uniblox@localhost:5432/uniblox"
)
_parsed = urlparse(_BASE_URL)
_db_name = _parsed.path.lstrip("/")
_TEST_DB = _db_name + "_test"
_TEST_URL = urlunparse(_parsed._replace(path="/" + _TEST_DB))
os.environ["DATABASE_URL"] = _TEST_URL


def _ensure_test_database() -> None:
    """Create the test database if it doesn't exist (connect to `postgres`)."""

    async def _create() -> None:
        conn = await asyncpg.connect(
            user=_parsed.username,
            password=_parsed.password,
            host=_parsed.hostname,
            port=_parsed.port or 5432,
            database="postgres",
        )
        try:
            await conn.execute(f'CREATE DATABASE "{_TEST_DB}"')
        except asyncpg.DuplicateDatabaseError:
            pass
        finally:
            await conn.close()

    asyncio.run(_create())


_ensure_test_database()

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

ADMIN_HEADERS = {"X-Admin-Token": get_settings().admin_token}

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session", autouse=True)
async def _clean():
    """Reset all tables before each test for isolation."""
    table_names = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    async with engine.begin() as conn:
        from sqlalchemy import text

        await conn.execute(
            text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE")
        )
    yield


@pytest_asyncio.fixture(loop_scope="session")
async def client():
    import httpx

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as c:
        yield c


@pytest_asyncio.fixture(loop_scope="session")
async def session():
    async with SessionLocal() as s:
        yield s


@pytest_asyncio.fixture(loop_scope="session")
async def make_product(session):
    """Return a coroutine that inserts a product and returns its id."""
    from app.models import Product

    async def _make(name: str, price_cents: int, inventory: int) -> int:
        p = Product(name=name, price_cents=price_cents, inventory=inventory)
        session.add(p)
        await session.commit()
        await session.refresh(p)
        return p.id

    return _make
