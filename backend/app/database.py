"""Async SQLAlchemy engine and session factory.

We use READ COMMITTED (PostgreSQL's default) and rely on explicit row locks
(`SELECT ... FOR UPDATE`) plus guarded conditional UPDATEs to enforce invariants.
See DECISIONS.md for why this beats SERIALIZABLE-with-retries for this workload.
"""
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, future=True, pool_pre_ping=True)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request."""
    async with SessionLocal() as session:
        yield session
