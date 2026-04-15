"""Backup and Restore API.

Provides one-click backup (SQLite + marketplace + config -> zip)
and one-click restore (zip -> restore all data).
"""

import json
import zipfile
import tempfile
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.db import get_db
from app.core.paths import marketplace_capabilities_dir, marketplace_bindings_dir

router = APIRouter()


@router.post("/backup")
async def backup_all():
    """Create a full backup zip containing:
    - app.db (SQLite database)
    - marketplace/ (capability and binding templates)
    - meta.json (backup metadata)
    """
    try:
        tmp_dir = tempfile.mkdtemp()
        zip_path = Path(tmp_dir) / "backup.zip"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Add SQLite database
            db_path = Path(settings.app_db_path)
            if db_path.exists():
                zf.write(str(db_path), "app.db")

            # Add checkpoint database
            cp_path = Path(settings.checkpoint_db_path)
            if cp_path.exists():
                zf.write(str(cp_path), "checkpoints.db")

            # Add marketplace capabilities
            cap_dir = marketplace_capabilities_dir()
            for f in cap_dir.glob("*.json"):
                zf.write(str(f), f"marketplace/capabilities/{f.name}")

            # Add marketplace bindings
            bind_dir = marketplace_bindings_dir()
            for f in bind_dir.glob("*.json"):
                zf.write(str(f), f"marketplace/bindings/{f.name}")

            # Add metadata
            meta = {
                "version": "0.1.0",
                "created_at": datetime.utcnow().isoformat(),
                "app_mode": settings.app_mode,
            }
            zf.writestr("meta.json", json.dumps(meta, indent=2))

        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename=f"mcp-shelf-backup-{datetime.utcnow().strftime('%Y%m%d')}.zip",
        )
    except Exception as e:
        raise HTTPException(500, f"Backup failed: {e}")


@router.post("/restore")
async def restore_all(file: UploadFile = File(...)):
    """Restore from a backup zip.

    Replaces:
    - app.db (main database)
    - checkpoints.db (LangGraph checkpoints)
    - marketplace files
    """
    try:
        tmp_dir = tempfile.mkdtemp()
        zip_path = Path(tmp_dir) / "backup.zip"

        # Save uploaded file
        with open(zip_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Validate zip
        if not zipfile.is_zipfile(zip_path):
            raise HTTPException(400, "Invalid backup file (not a zip)")

        # Close current DB connection before restoring
        from app.core.db import close_db
        await close_db()

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()

            # Restore SQLite database
            if "app.db" in names:
                db_path = Path(settings.app_db_path)
                zf.extract("app.db", tmp_dir)
                shutil.copy2(Path(tmp_dir) / "app.db", db_path)

            # Restore checkpoint database
            if "checkpoints.db" in names:
                cp_path = Path(settings.checkpoint_db_path)
                zf.extract("checkpoints.db", tmp_dir)
                shutil.copy2(Path(tmp_dir) / "checkpoints.db", cp_path)

            # Restore marketplace files
            for name in names:
                if name.startswith("marketplace/"):
                    zf.extract(name, tmp_dir)
                    dest = Path("data") / name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(Path(tmp_dir) / name, dest)

        # Re-initialize DB connection
        from app.core.db import get_db
        await get_db()

        return {"status": "restored", "detail": "Data restored successfully. Please refresh."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Restore failed: {e}")
