"""PostgresState — async SQLAlchemy engine, session factory, and DeclarativeBase."""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from fablestar.core.config import DatabaseConfig

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class PostgresState:
    """
    Manages the persistent PostgreSQL database connection and sessions.
    """

    def __init__(self, config: DatabaseConfig):
        self.config = config

        # Build the async connection string
        # pattern: postgresql+asyncpg://user:password@host:port/dbname
        password_part = f":{config.password}" if config.password else ""
        self.url = f"postgresql+asyncpg://{config.user}{password_part}@{config.host}:{config.port}/{config.database}"

        self.engine = create_async_engine(
            self.url,
            pool_size=config.pool_size,
            max_overflow=10,
            echo=False,  # Set to True for SQL debugging
        )

        self.session_factory = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Dependency for getting a database session."""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def close(self):
        """Dispose of the engine connection pool."""
        await self.engine.dispose()
        logger.info("PostgreSQL connection closed.")
