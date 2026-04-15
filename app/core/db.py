from app.core.config import settings
from pathlib import Path
from typing import Optional

import aiosqlite

_db: Optional[aiosqlite.Connection] = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        db_path = Path(settings.app_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _db = await aiosqlite.connect(str(db_path))
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
    return _db


async def close_db():
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def init_db():
    """Initialize database with migration system."""
    from app.core.migrations import run_migrations
    await get_db()  # ensure connection
    await run_migrations()
