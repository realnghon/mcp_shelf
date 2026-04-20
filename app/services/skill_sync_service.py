"""Skill synchronization service (GitHub -> local skill packs)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from app.core.config import settings
from app.core.seed_data import ensure_skill_seed_files, seed_default_capabilities


class SkillSyncService:
    SUPERPOWERS_REPO = "https://github.com/obra/superpowers.git"

    async def sync_pack(self, pack: str) -> dict:
        pack_name = str(pack or "").strip().lower()
        if pack_name != "superpowers":
            raise ValueError(f"Pack '{pack_name}' does not support sync")
        return await self._sync_superpowers()

    async def _sync_superpowers(self) -> dict:
        """Sync superpowers repo and reseed capabilities."""
        ensure_skill_seed_files()

        super_root = settings.data_dir / "skills" / "superpowers"
        mirror_dir = super_root / ".mirror"
        skills_target = super_root / "skills"
        agents_target = super_root / "agents"
        commands_target = super_root / "commands"

        mirror_dir.parent.mkdir(parents=True, exist_ok=True)
        self._sync_repo(self.SUPERPOWERS_REPO, mirror_dir)

        self._replace_tree(mirror_dir / "skills", skills_target)
        if (mirror_dir / "agents").exists():
            self._replace_tree(mirror_dir / "agents", agents_target)
        if (mirror_dir / "commands").exists():
            self._replace_tree(mirror_dir / "commands", commands_target)

        await seed_default_capabilities(prune_missing=True)

        skill_count = len(list(skills_target.glob("*/SKILL.md")))
        return {
            "ok": True,
            "pack": "superpowers",
            "skill_count": skill_count,
            "repo": self.SUPERPOWERS_REPO,
        }

    @staticmethod
    def _sync_repo(repo_url: str, target_dir: Path) -> None:
        if (target_dir / ".git").exists():
            SkillSyncService._run(["git", "-C", str(target_dir), "fetch", "--depth", "1", "origin", "main"])
            SkillSyncService._run(["git", "-C", str(target_dir), "reset", "--hard", "origin/main"])
            return
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        SkillSyncService._run(["git", "clone", "--depth", "1", repo_url, str(target_dir)])

    @staticmethod
    def _replace_tree(src: Path, dst: Path) -> None:
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst)

    @staticmethod
    def _run(cmd: list[str]) -> None:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            stdout = (proc.stdout or "").strip()
            detail = stderr or stdout or f"command failed: {' '.join(cmd)}"
            raise RuntimeError(detail)
