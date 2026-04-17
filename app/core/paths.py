from pathlib import Path

from app.core.config import settings


def ensure_data_dirs():
    dirs = [
        settings.data_dir,
        settings.data_dir / "marketplace" / "capabilities",
        settings.data_dir / "marketplace" / "bindings",
        settings.data_dir / "marketplace" / "bundles",
        settings.data_dir / "exports",
        settings.data_dir / "imports",
        settings.data_dir / "icons",
        settings.data_dir / "seeds",
        settings.data_dir / "memory",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def marketplace_capabilities_dir() -> Path:
    return settings.data_dir / "marketplace" / "capabilities"


def marketplace_bindings_dir() -> Path:
    return settings.data_dir / "marketplace" / "bindings"


def exports_dir() -> Path:
    return settings.data_dir / "exports"
