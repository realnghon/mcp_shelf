"""Seed default capabilities and skills for first-run experience."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from app.core.config import settings
from app.repositories.capability_repo import CapabilityRepo

logger = logging.getLogger(__name__)


async def seed_default_capabilities(prune_missing: bool = False) -> None:
    """Seed built-in starter skill capabilities if missing."""
    repo = CapabilityRepo()
    skills_root = settings.data_dir / "skills" / "superpowers" / "skills"
    if not skills_root.exists():
        logger.info("Skip seeding superpowers skills; root not found: %s", skills_root)
        return

    seeded = 0
    seen_slugs: set[str] = set()
    for skill_entry in sorted(skills_root.glob("*/SKILL.md")):
        skill_dir = skill_entry.parent
        skill_key = skill_dir.name
        slug = f"superpowers-{skill_key}"
        name, description = _extract_skill_name_description(skill_entry)
        include_files = _list_include_files(skill_dir)

        payload = {
            "kind": "skill",
            "name": name or f"Superpowers: {skill_key}",
            "slug": slug,
            "description": description or f"Skill from obra/superpowers: {skill_key}",
            "category": "skill",
            "tags": ["superpowers", "skill", skill_key],
            "version": "0.1.0",
            "visibility": "public",
            "type": "prompt",
            "source_type": "custom",
            "source_id": f"skill.superpowers.{skill_key}",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "config_schema": {"type": "object"},
            "connection_config": {
                "path": str(skill_dir),
                "entry_file": "SKILL.md",
                "include_files": include_files,
            },
            "schema_status": "valid",
            "metadata": {
                "skill_pack": "superpowers",
                "upstream": "https://github.com/obra/superpowers",
                "upstream_skill": f"skills/{skill_key}",
            },
        }
        seen_slugs.add(slug)

        existing = await repo.get_by_slug(slug)
        if existing:
            await repo.update(existing["id"], payload)
        else:
            await repo.create(payload)
            seeded += 1

    if seeded:
        logger.info("Seeded %d superpowers skills", seeded)
    if prune_missing:
        skills, _ = await repo.list_all(
            kind="skill",
            page=1,
            page_size=2000,
            sort_by="name",
            sort_order="asc",
        )
        for cap in skills:
            slug = str(cap.get("slug") or "")
            source_id = str(cap.get("source_id") or "")
            if not slug.startswith("superpowers-"):
                continue
            if not source_id.startswith("skill.superpowers."):
                continue
            if slug in seen_slugs:
                continue
            await repo.delete(cap["id"])
            logger.info("Removed stale superpowers skill capability: %s", slug)


def ensure_skill_seed_files() -> None:
    """Ensure local starter skill directories exist."""
    root = settings.data_dir / "skills" / "superpowers" / "skills"
    root.mkdir(parents=True, exist_ok=True)


def _extract_skill_name_description(skill_entry: Path) -> tuple[str, str]:
    text = skill_entry.read_text(encoding="utf-8", errors="replace")
    head = "\n".join(text.splitlines()[:40])
    name = ""
    description = ""

    m_name = re.search(r"^name:\s*(.+)$", head, flags=re.MULTILINE | re.IGNORECASE)
    if m_name:
        name = str(m_name.group(1)).strip().strip('"\'')

    m_desc = re.search(r"^description:\s*(.+)$", head, flags=re.MULTILINE | re.IGNORECASE)
    if m_desc:
        description = str(m_desc.group(1)).strip().strip('"\'')

    if not name:
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("#"):
                name = line.lstrip("#").strip()
                break

    return name, description


def _list_include_files(skill_dir: Path) -> list[str]:
    include: list[str] = []
    for f in skill_dir.rglob("*"):
        if not f.is_file():
            continue
        if f.name == "SKILL.md":
            continue
        rel = f.relative_to(skill_dir).as_posix()
        include.append(rel)
    return include
