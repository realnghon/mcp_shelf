"""Initialize the SQLite database."""
import asyncio
from pathlib import Path

# Add project root to path so we can import app
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.db import init_db


async def main():
    print("Initializing database...")
    await init_db()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
