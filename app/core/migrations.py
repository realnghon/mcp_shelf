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
SCHEMA_VERSION = 6

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
    # v2 -> v3: Add unified registry capability fields and capability_tests table
    """ALTER TABLE capabilities ADD COLUMN type TEXT NOT NULL DEFAULT 'tool';
    ALTER TABLE capabilities ADD COLUMN source_type TEXT NOT NULL DEFAULT 'custom';
    ALTER TABLE capabilities ADD COLUMN source_id TEXT;
    ALTER TABLE capabilities ADD COLUMN input_schema TEXT NOT NULL DEFAULT '{}';
    ALTER TABLE capabilities ADD COLUMN output_schema TEXT NOT NULL DEFAULT '{}';
    ALTER TABLE capabilities ADD COLUMN schema_status TEXT;
    ALTER TABLE capabilities ADD COLUMN last_test_status TEXT;
    ALTER TABLE capabilities ADD COLUMN last_tested_at TEXT;
    ALTER TABLE capabilities ADD COLUMN last_latency_ms INTEGER;

    CREATE TABLE IF NOT EXISTS capability_tests (
        id TEXT PRIMARY KEY,
        capability_id TEXT NOT NULL,
        status TEXT NOT NULL,
        latency_ms INTEGER,
        request_payload TEXT NOT NULL DEFAULT '{}',
        response_payload TEXT NOT NULL DEFAULT '{}',
        error_message TEXT,
        tested_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(capability_id) REFERENCES capabilities(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_capability_tests_capability_id
        ON capability_tests(capability_id, tested_at DESC);
    """,
    # v3 -> v4: Add tool event type for runtime_messages
    """ALTER TABLE runtime_messages
       ADD COLUMN tool_event_type TEXT NOT NULL DEFAULT 'result';
    """,
    # v4 -> v5: Cleanup legacy placeholder binding records
    """-- no-op; handled in python migration helper for compatibility checks
    """,
    # v5 -> v6: Cleanup legacy placeholder echo capability records
    """-- no-op; handled in python migration helper for compatibility checks
    """,
]


async def _table_exists(db: aiosqlite.Connection, table_name: str) -> bool:
    cursor = await db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        [table_name],
    )
    return await cursor.fetchone() is not None


async def _column_exists(db: aiosqlite.Connection, table_name: str, column_name: str) -> bool:
    cursor = await db.execute(f"PRAGMA table_info({table_name})")
    rows = await cursor.fetchall()
    return any(row[1] == column_name for row in rows)


async def _ensure_v3_capability_fields(db: aiosqlite.Connection):
    capability_columns: list[tuple[str, str]] = [
        ("type", "TEXT NOT NULL DEFAULT 'tool'"),
        ("source_type", "TEXT NOT NULL DEFAULT 'custom'"),
        ("source_id", "TEXT"),
        ("input_schema", "TEXT NOT NULL DEFAULT '{}'"),
        ("output_schema", "TEXT NOT NULL DEFAULT '{}'"),
        ("schema_status", "TEXT"),
        ("last_test_status", "TEXT"),
        ("last_tested_at", "TEXT"),
        ("last_latency_ms", "INTEGER"),
    ]
    for column_name, column_sql in capability_columns:
        if not await _column_exists(db, "capabilities", column_name):
            await db.execute(f"ALTER TABLE capabilities ADD COLUMN {column_name} {column_sql}")

    await db.execute(
        """CREATE TABLE IF NOT EXISTS capability_tests (
            id TEXT PRIMARY KEY,
            capability_id TEXT NOT NULL,
            status TEXT NOT NULL,
            latency_ms INTEGER,
            request_payload TEXT NOT NULL DEFAULT '{}',
            response_payload TEXT NOT NULL DEFAULT '{}',
            error_message TEXT,
            tested_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(capability_id) REFERENCES capabilities(id) ON DELETE CASCADE
        )"""
    )
    await db.execute(
        """CREATE INDEX IF NOT EXISTS idx_capability_tests_capability_id
        ON capability_tests(capability_id, tested_at DESC)"""
    )
    await db.commit()


async def _ensure_v4_runtime_message_fields(db: aiosqlite.Connection):
    if not await _table_exists(db, "runtime_messages"):
        return
    if not await _column_exists(db, "runtime_messages", "tool_event_type"):
        await db.execute(
            "ALTER TABLE runtime_messages ADD COLUMN tool_event_type TEXT NOT NULL DEFAULT 'result'"
        )
    await db.commit()


async def _cleanup_v5_legacy_placeholder_bindings(db: aiosqlite.Connection):
    if not await _table_exists(db, "bindings"):
        return

    await db.execute(
        """
        DELETE FROM bindings
        WHERE
            lower(replace(name, '_', ' ')) = 'test agent'
            AND (description IS NULL OR trim(description) = '')
            AND model_key = 'openai:gpt-4.1'
            AND coalesce(system_prompt, '') = 'You are a test agent.'
            AND max_steps = 5
            AND allow_shell = 0
            AND visibility = 'private'
            AND NOT EXISTS (
                SELECT 1 FROM binding_capabilities bc WHERE bc.binding_id = bindings.id
            )
        """
    )
    await db.commit()


async def _cleanup_v6_legacy_placeholder_echo_capability(db: aiosqlite.Connection):
    if not await _table_exists(db, "capabilities"):
        return

    await db.execute(
        """
        DELETE FROM capabilities
        WHERE
            slug = 'echo-tool'
            AND name = 'Echo Tool'
            AND coalesce(description, '') = 'Simple echo tool'
            AND kind = 'tool'
            AND source_type = 'custom'
            AND coalesce(category, '') = 'utility'
            AND version = '0.1.0'
            AND status = 'active'
        """
    )
    await db.commit()


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
        has_capabilities = await _table_exists(db, "capabilities")
        has_meta = await _table_exists(db, "_meta")

        if not has_capabilities:
            schema_path = Path(__file__).parent.parent.parent / "scripts" / "schema.sql"
            if schema_path.exists():
                schema_sql = schema_path.read_text(encoding="utf-8")
                await db.executescript(schema_sql)
            await db.executescript(MIGRATIONS[0])
            await set_schema_version(db, SCHEMA_VERSION)
            logger.info("Database initialized at schema version %d", SCHEMA_VERSION)
            return

        if not has_meta:
            await db.executescript(MIGRATIONS[0])

        current_version = 2
        if await _column_exists(db, "capabilities", "type"):
            current_version = 3
        if await _column_exists(db, "runtime_messages", "tool_event_type"):
            current_version = 4
        if current_version == 4:
            await _cleanup_v5_legacy_placeholder_bindings(db)
            current_version = 5
        if current_version == 5:
            await _cleanup_v6_legacy_placeholder_echo_capability(db)
            current_version = 6
        await set_schema_version(db, current_version)

    for i in range(current_version, SCHEMA_VERSION):
        migration_idx = i
        if migration_idx < len(MIGRATIONS):
            logger.info(f"Applying migration v{i} -> v{i + 1}")
            if i == 2:
                await _ensure_v3_capability_fields(db)
            elif i == 3:
                await _ensure_v4_runtime_message_fields(db)
            elif i == 4:
                await _cleanup_v5_legacy_placeholder_bindings(db)
            elif i == 5:
                await _cleanup_v6_legacy_placeholder_echo_capability(db)
            else:
                await db.executescript(MIGRATIONS[migration_idx])
            await set_schema_version(db, i + 1)

    if current_version < SCHEMA_VERSION:
        logger.info("Database migrated to schema version %d", SCHEMA_VERSION)
    else:
        logger.info("Database schema is up to date (v%d)", SCHEMA_VERSION)
