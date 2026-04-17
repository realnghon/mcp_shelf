from langgraph.checkpoint.memory import MemorySaver

import aiosqlite

from app.core.config import settings


def get_checkpointer():
    """Get the appropriate checkpointer based on config."""
    if settings.use_memory_checkpoint:
        return MemorySaver()

    # SQLite checkpointer for lite mode
    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        from pathlib import Path
        from app.core.config import settings as s

        db_path = Path(s.checkpoint_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # Return a factory that creates the checkpointer
        return _SqliteCheckpointerFactory(str(db_path))
    except ImportError:
        return MemorySaver()


class _SqliteCheckpointerFactory:
    """Factory that creates async SQLite checkpointer on demand."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._checkpointer = None

    async def get(self):
        if self._checkpointer is None:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
            conn = await aiosqlite.connect(self.db_path)
            self._checkpointer = AsyncSqliteSaver(conn)
            await self._checkpointer.setup()
        return self._checkpointer
