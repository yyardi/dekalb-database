"""
Database connection pool management.
Uses asyncpg for async PostgreSQL access throughout the FastAPI app.

On startup, if the target database (trade_tracker) doesn't exist yet — e.g.
because Postgres volume was carried over from before the monorepo split — this
module creates it automatically and applies the schema, so the service never
crashes due to a missing database.
"""
import asyncpg
import logging
import os

import config

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None

# Schema file is mounted into the container at this path (see docker-compose.yml)
_SCHEMA_FILE = "/etc/schemas/trade_tracker_schema.sql"


async def _ensure_db_exists() -> None:
    """
    Connect to the default 'postgres' database and create trade_tracker if
    it doesn't exist, then apply the schema DDL.
    """
    logger.warning(
        "Database '%s' not found — creating it now...", config.POSTGRES_DB
    )

    # Connect to the maintenance DB (always exists)
    conn = await asyncpg.connect(
        host=config.DB_HOST,
        port=config.POSTGRES_PORT,
        database="postgres",
        user=config.POSTGRES_USER,
        password=config.POSTGRES_PASSWORD,
    )
    try:
        await conn.execute(f'CREATE DATABASE "{config.POSTGRES_DB}"')
        logger.info("Created database '%s'", config.POSTGRES_DB)
    finally:
        await conn.close()

    # Now apply the schema to the new database
    if os.path.exists(_SCHEMA_FILE):
        schema_conn = await asyncpg.connect(
            host=config.DB_HOST,
            port=config.POSTGRES_PORT,
            database=config.POSTGRES_DB,
            user=config.POSTGRES_USER,
            password=config.POSTGRES_PASSWORD,
        )
        try:
            with open(_SCHEMA_FILE) as f:
                ddl = f.read()
            await schema_conn.execute(ddl)
            logger.info("Schema applied to '%s'", config.POSTGRES_DB)
        finally:
            await schema_conn.close()
    else:
        logger.warning(
            "Schema file not found at %s — database created but tables not initialised",
            _SCHEMA_FILE,
        )


async def init_pool() -> None:
    """Create the connection pool. Called once at application startup."""
    global _pool
    try:
        _pool = await asyncpg.create_pool(
            host=config.DB_HOST,
            port=config.POSTGRES_PORT,
            database=config.POSTGRES_DB,
            user=config.POSTGRES_USER,
            password=config.POSTGRES_PASSWORD,
            min_size=config.DB_MIN_CONNECTIONS,
            max_size=config.DB_MAX_CONNECTIONS,
        )
    except asyncpg.InvalidCatalogNameError:
        # Database doesn't exist yet — create it, then retry
        await _ensure_db_exists()
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
