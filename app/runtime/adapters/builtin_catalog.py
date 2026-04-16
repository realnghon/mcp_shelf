"""Builtin capability manifest loader."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _builtin_capabilities_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "builtin" / "capabilities"


def _manifest_to_capability(manifest: dict[str, Any]) -> dict[str, Any]:
    slug = manifest["slug"]
    builtin_id = f"builtin:{slug}"
    runtime = dict(manifest.get("runtime") or {})

    capability = dict(manifest)
    capability["id"] = builtin_id
    capability["source_id"] = builtin_id
    capability["type"] = manifest.get("type") or manifest.get("kind") or "tool"
    capability["source_type"] = "builtin"
    capability["input_schema"] = manifest.get("input_schema") or {}
    capability["output_schema"] = manifest.get("output_schema") or {}
    capability["config_schema"] = manifest.get("config_schema") or {}
    capability["connection_config"] = runtime
    capability["schema_status"] = "valid"
    capability["is_builtin"] = True
    capability["metadata"] = dict(manifest.get("metadata") or {})
    capability.setdefault("status", "active")
    capability.setdefault("version", "0.1.0")
    capability.setdefault("visibility", "public")
    capability.setdefault("tags", [])
    capability.setdefault("description", "")
    capability.setdefault("category", None)
    capability.setdefault("owner_id", None)
    capability.setdefault("last_test_status", None)
    capability.setdefault("last_tested_at", None)
    capability.setdefault("last_latency_ms", None)
    return capability


def load_builtin_capabilities() -> list[dict[str, Any]]:
    """Load builtin capabilities from manifest files."""
    capabilities: list[dict[str, Any]] = []
    for manifest_path in sorted(_builtin_capabilities_dir().glob("*.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        capabilities.append(_manifest_to_capability(manifest))
    return capabilities
