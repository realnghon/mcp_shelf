import aiosqlite
import pytest

from app.core import db as db_module
from app.core.migrations import run_migrations
from app.repositories.capability_repo import CapabilityRepo
from app.schemas.capability import CapabilityCreate, CapabilityOut, CapabilityUpdate


def test_capability_create_accepts_unified_registry_fields():
    capability = CapabilityCreate(
        kind="tool",
        name="Weather Tool",
        slug="weather-tool",
        type="resource",
        source_type="mcp_server",
        source_id="server-123",
        input_schema={"type": "object", "properties": {"city": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"forecast": {"type": "string"}}},
        schema_status="valid",
        last_test_status="passed",
        last_tested_at="2026-04-16T12:00:00+00:00",
        last_latency_ms=8,
    )

    assert capability.type == "resource"
    assert capability.source_type == "mcp_server"
    assert capability.source_id == "server-123"
    assert capability.input_schema == {"type": "object", "properties": {"city": {"type": "string"}}}
    assert capability.output_schema == {
        "type": "object",
        "properties": {"forecast": {"type": "string"}},
    }
    assert capability.schema_status == "valid"
    assert capability.last_test_status == "passed"
    assert capability.last_tested_at == "2026-04-16T12:00:00+00:00"
    assert capability.last_latency_ms == 8


def test_capability_update_accepts_schema_and_test_status_fields():
    update = CapabilityUpdate(
        type="workflow",
        source_type="plugin",
        source_id="plugin.demo",
        input_schema={"type": "object"},
        output_schema={"type": "array"},
        schema_status="valid",
        last_test_status="passed",
        last_tested_at="2026-04-16T12:00:00+00:00",
        last_latency_ms=42,
    )

    assert update.type == "workflow"
    assert update.source_type == "plugin"
    assert update.source_id == "plugin.demo"
    assert update.schema_status == "valid"
    assert update.last_test_status == "passed"
    assert update.last_tested_at == "2026-04-16T12:00:00+00:00"
    assert update.last_latency_ms == 42


def test_capability_out_exposes_unified_registry_fields():
    capability = CapabilityOut(
        id="cap-1",
        kind="tool",
        name="Weather Tool",
        slug="weather-tool",
        description=None,
        category=None,
        tags=[],
        version="0.1.0",
        visibility="public",
        status="active",
        owner_id=None,
        type="prompt",
        source_type="builtin",
        source_id="builtin.weather",
        input_schema={"type": "object"},
        output_schema={"type": "string"},
        config_schema={"type": "object"},
        connection_config={},
        schema_status="valid",
        last_test_status="passed",
        last_tested_at="2026-04-16T12:00:00+00:00",
        last_latency_ms=12,
        metadata={},
        created_at="2026-04-16T12:00:00+00:00",
        updated_at="2026-04-16T12:00:01+00:00",
    )

    assert capability.type == "prompt"
    assert capability.source_type == "builtin"
    assert capability.source_id == "builtin.weather"
    assert capability.input_schema == {"type": "object"}
    assert capability.output_schema == {"type": "string"}
    assert capability.schema_status == "valid"
    assert capability.last_test_status == "passed"
    assert capability.last_tested_at == "2026-04-16T12:00:00+00:00"
    assert capability.last_latency_ms == 12


@pytest.mark.asyncio
async def test_run_migrations_initializes_new_database_with_unified_registry_fields(tmp_path):
    db_path = tmp_path / "app.db"
    original_path = db_module.settings.app_db_path
    db_module._db = None
    db_module.settings.app_db_path = str(db_path)

    try:
        await run_migrations()
        await run_migrations()
        db = await db_module.get_db()
        cursor = await db.execute("PRAGMA table_info(capabilities)")
        columns = {row[1] for row in await cursor.fetchall()}
        assert {"type", "source_type", "source_id", "input_schema", "output_schema"} <= columns

        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'capability_tests'"
        )
        assert await cursor.fetchone() is not None
    finally:
        await db_module.close_db()
        db_module.settings.app_db_path = original_path
        db_module._db = None


@pytest.mark.asyncio
async def test_run_migrations_upgrades_legacy_database_without_meta(tmp_path):
    db_path = tmp_path / "legacy.db"
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(
            """
            CREATE TABLE capabilities (
              id TEXT PRIMARY KEY,
              kind TEXT NOT NULL,
              name TEXT NOT NULL,
              slug TEXT NOT NULL UNIQUE,
              description TEXT,
              category TEXT,
              tags TEXT NOT NULL DEFAULT '[]',
              version TEXT NOT NULL DEFAULT '0.1.0',
              visibility TEXT NOT NULL DEFAULT 'public',
              status TEXT NOT NULL DEFAULT 'active',
              owner_id TEXT,
              config_schema TEXT NOT NULL DEFAULT '{}',
              connection_config TEXT NOT NULL DEFAULT '{}',
              metadata TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )
        await db.commit()

    original_path = db_module.settings.app_db_path
    db_module._db = None
    db_module.settings.app_db_path = str(db_path)

    try:
        await run_migrations()
        await run_migrations()
        db = await db_module.get_db()
        cursor = await db.execute("PRAGMA table_info(capabilities)")
        columns = {row[1] for row in await cursor.fetchall()}
        assert "type" in columns
        assert "input_schema" in columns

        cursor = await db.execute("SELECT value FROM _meta WHERE key = 'schema_version'")
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "6"
    finally:
        await db_module.close_db()
        db_module.settings.app_db_path = original_path
        db_module._db = None




@pytest.mark.asyncio
async def test_run_migrations_completes_partially_upgraded_database(tmp_path):
    db_path = tmp_path / "partial.db"
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(
            """
            CREATE TABLE capabilities (
              id TEXT PRIMARY KEY,
              kind TEXT NOT NULL,
              name TEXT NOT NULL,
              slug TEXT NOT NULL UNIQUE,
              description TEXT,
              category TEXT,
              tags TEXT NOT NULL DEFAULT '[]',
              version TEXT NOT NULL DEFAULT '0.1.0',
              visibility TEXT NOT NULL DEFAULT 'public',
              status TEXT NOT NULL DEFAULT 'active',
              owner_id TEXT,
              type TEXT NOT NULL DEFAULT 'tool',
              config_schema TEXT NOT NULL DEFAULT '{}',
              connection_config TEXT NOT NULL DEFAULT '{}',
              metadata TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE _meta (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            INSERT INTO _meta (key, value) VALUES ('schema_version', '2');
            """
        )
        await db.commit()

    original_path = db_module.settings.app_db_path
    db_module._db = None
    db_module.settings.app_db_path = str(db_path)

    try:
        await run_migrations()
        await run_migrations()
        db = await db_module.get_db()
        cursor = await db.execute("PRAGMA table_info(capabilities)")
        columns = {row[1] for row in await cursor.fetchall()}
        assert "type" in columns
        assert "source_type" in columns
        assert "output_schema" in columns

        cursor = await db.execute("SELECT value FROM _meta WHERE key = 'schema_version'")
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "6"
    finally:
        await db_module.close_db()
        db_module.settings.app_db_path = original_path
        db_module._db = None


@pytest.mark.asyncio
async def test_run_migrations_v6_removes_legacy_echo_tool_placeholder(tmp_path):
    db_path = tmp_path / "legacy_echo.db"
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(
            """
            CREATE TABLE capabilities (
              id TEXT PRIMARY KEY,
              kind TEXT NOT NULL,
              name TEXT NOT NULL,
              slug TEXT NOT NULL UNIQUE,
              description TEXT,
              category TEXT,
              tags TEXT NOT NULL DEFAULT '[]',
              version TEXT NOT NULL DEFAULT '0.1.0',
              visibility TEXT NOT NULL DEFAULT 'public',
              status TEXT NOT NULL DEFAULT 'active',
              owner_id TEXT,
              type TEXT NOT NULL DEFAULT 'tool',
              source_type TEXT NOT NULL DEFAULT 'custom',
              source_id TEXT,
              input_schema TEXT NOT NULL DEFAULT '{}',
              output_schema TEXT NOT NULL DEFAULT '{}',
              config_schema TEXT NOT NULL DEFAULT '{}',
              connection_config TEXT NOT NULL DEFAULT '{}',
              schema_status TEXT,
              last_test_status TEXT,
              last_tested_at TEXT,
              last_latency_ms INTEGER,
              metadata TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE _meta (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            INSERT INTO _meta (key, value) VALUES ('schema_version', '5');
            INSERT INTO capabilities (
              id, kind, name, slug, description, category, tags, version, visibility, status,
              owner_id, type, source_type, source_id, input_schema, output_schema, config_schema,
              connection_config, schema_status, last_test_status, last_tested_at, last_latency_ms,
              metadata, created_at, updated_at
            ) VALUES (
              'cap_echo_1', 'tool', 'Echo Tool', 'echo-tool', 'Simple echo tool', 'utility', '[]',
              '0.1.0', 'public', 'active', NULL, 'tool', 'custom', NULL, '{}', '{}', '{}', '{}',
              NULL, NULL, NULL, NULL, '{}', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
            );
            """
        )
        await db.commit()

    original_path = db_module.settings.app_db_path
    db_module._db = None
    db_module.settings.app_db_path = str(db_path)

    try:
        await run_migrations()
        db = await db_module.get_db()

        cursor = await db.execute("SELECT value FROM _meta WHERE key = 'schema_version'")
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "6"

        cursor = await db.execute("SELECT COUNT(*) FROM capabilities WHERE slug = 'echo-tool'")
        count_row = await cursor.fetchone()
        assert count_row is not None
        assert int(count_row[0]) == 0
    finally:
        await db_module.close_db()
        db_module.settings.app_db_path = original_path
        db_module._db = None
    db_path = tmp_path / "repo.db"
    original_path = db_module.settings.app_db_path
    db_module._db = None
    db_module.settings.app_db_path = str(db_path)

    try:
        await run_migrations()
        repo = CapabilityRepo()
        created = await repo.create(
            {
                "kind": "skill",
                "name": "Calculator",
                "slug": "calculator",
                "type": "tool",
                "source_type": "builtin",
                "source_id": "builtin:calculator",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "config_schema": {"type": "object"},
                "schema_status": "valid",
            }
        )
        assert created["kind"] == "skill"
        assert created["source_type"] == "builtin"
        assert created["input_schema"]["type"] == "object"

        updated = await repo.update(
            created["id"],
            {
                "source_id": "builtin:calculator:v2",
                "last_test_status": "passed",
                "last_latency_ms": 23,
            },
        )
        assert updated is not None
        assert updated["source_id"] == "builtin:calculator:v2"
        assert updated["last_test_status"] == "passed"
        assert updated["last_latency_ms"] == 23
    finally:
        await db_module.close_db()
        db_module.settings.app_db_path = original_path
        db_module._db = None
