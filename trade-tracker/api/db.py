"""
Database connection pool management.
Uses asyncpg for async PostgreSQL access throughout the FastAPI app.
"""
import asyncpg
import logging

import config

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    """Create the connection pool. Called once at application startup."""
    global _pool
    _pool = await asyncpg.create_pool(
        host=config.DB_HOST,
        port=config.POSTGRES_PORT,
        database=config.POSTGRES_DB,
        user=config.POSTGRES_USER,
        password=config.POSTGRES_PASSWORD,
        min_size=config.DB_MIN_CONNECTIONS,
        max_size=config.DB_MAX_CONNECTIONS,
    )
    logger.info(
        "PostgreSQL pool created: %s:%s/%s",
        config.DB_HOST,
        config.POSTGRES_PORT,
        config.POSTGRES_DB,
    )


async def close_pool() -> None:
    """Close the connection pool. Called at application shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        logger.info("PostgreSQL pool closed")


def get_pool() -> asyncpg.Pool:
    """Return the active pool. Raises if init_pool() was never called."""
    if _pool is None:
        raise RuntimeError("Database pool has not been initialized")
    return _pool
