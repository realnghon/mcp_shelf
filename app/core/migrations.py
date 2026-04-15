"""Database migration system.

Tracks schema version in a _meta table. On startup, checks current version
and applies pending migrations in order. Each migration is a SQL string.
"""

import logging
from pathlib import Path

import aiosqlite

from app.core.db import get_db

logger = logging.getLogger(__name__)

# Current schema version - bump this when schema changes
SCHEMA_VERSION = 2

# Migrations: index 0 = v0->v1, index 1 = v1->v2, etc.
MIGRATIONS: list[str] = [
    # v0 -> v1: Initial schema (applied via schema.sql)
    """CREATE TABLE IF NOT EXISTS _meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    INSERT OR IGNORE INTO _meta (key, value) VALUES ('schema_version', '0');
    """,
    # v1 -> v2: Add llm_configs table
    """CREATE TABLE IF NOT EXISTS llm_configs (
        id TEXT PRIMARY KEY,
        provider TEXT NOT NULL,
        name TEXT NOT NULL,
        api_key TEXT,
        base_url TEXT,
        default_model TEXT,
        is_default INTEGER NOT NULL DEFAULT 0,
        extra_config TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
]


async def get_schema_version(db: aiosqlite.Connection) -> int:
    """Get current schema version from _meta table."""
    try:
        row = await db.execute("SELECT value FROM _meta WHERE key = 'schema_version'")
        result = await row.fetchone()
        if result:
            return int(result[0])
    except Exception:
        pass
    return 0


async def set_schema_version(db: aiosqlite.Connection, version: int):
    """Set schema version in _meta table."""
    await db.execute(
        "INSERT OR REPLACE INTO _meta (key, value) VALUES ('schema_version', ?)",
        [str(version)],
    )
    await db.commit()


async def run_migrations():
    """Check and apply pending migrations."""
    db = await get_db()
    current_version = await get_schema_version(db)

    if current_version == 0:
        # First run: apply full schema
        schema_path = Path(__file__).parent.parent.parent / "scripts" / "schema.sql"
        if schema_path.exists():
            schema_sql = schema_path.read_text(encoding="utf-8")
            await db.executescript(schema_sql)
        # Apply v0->v1 migration (creates _meta table)
        await db.executescript(MIGRATIONS[0])
        await set_schema_version(db, 1)
        current_version = 1
        logger.info("Database initialized at schema version 1")

    # Apply any additional migrations
    for i in range(current_version, SCHEMA_VERSION):
        migration_idx = i  # MIGRATIONS[i] = v(i)->v(i+1)
        if migration_idx < len(MIGRATIONS):
            logger.info(f"Applying migration v{i} -> v{i + 1}")
            await db.executescript(MIGRATIONS[migration_idx])
            await set_schema_version(db, i + 1)

    if current_version < SCHEMA_VERSION:
        logger.info("Database migrated to schema version %d" % SCHEMA_VERSION)
    else:
        logger.info("Database schema is up to date (v%d)" % SCHEMA_VERSION)
