"""Skill pack management router."""

from fastapi import APIRouter, HTTPException

from app.services.skill_sync_service import SkillSyncService

router = APIRouter()
svc = SkillSyncService()


@router.post("/sync/{pack}")
async def sync_skill_pack(pack: str):
    try:
        return await svc.sync_pack(pack)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Sync skill pack failed: {exc}") from exc
