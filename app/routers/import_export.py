"""Import/Export and Marketplace router."""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

from app.core.paths import marketplace_capabilities_dir, marketplace_bindings_dir, exports_dir
from app.services.registry_service import RegistryService
from app.services.binding_service import BindingService
from app.schemas.capability import CapabilityCreate
from app.schemas.binding import BindingCreate

router = APIRouter()
reg_svc = RegistryService()
bind_svc = BindingService()


# --- Marketplace ---

@router.get("/marketplace/capabilities")
async def list_marketplace_capabilities():
    cap_dir = marketplace_capabilities_dir()
    results = []
    for f in cap_dir.glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        data["_file"] = f.name
        results.append(data)
    return results


@router.get("/marketplace/bindings")
async def list_marketplace_bindings():
    bind_dir = marketplace_bindings_dir()
    results = []
    for f in bind_dir.glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        data["_file"] = f.name
        results.append(data)
    return results


# --- Import ---

@router.post("/import/capability", status_code=201)
async def import_capability(data: dict):
    """Import a capability from JSON data."""
    try:
        cap = CapabilityCreate(**data)
        return await reg_svc.create_capability(cap)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/import/binding", status_code=201)
async def import_binding(data: dict):
    """Import a binding from JSON data."""
    try:
        caps_data = data.pop("capabilities", [])
        binding = BindingCreate(**data)
        record = await bind_svc.create_binding(binding)

        # Attach capabilities by slug
        for cap_ref in caps_data:
            slug = cap_ref.get("slug", "")
            existing_cap = await reg_svc.get_by_slug(slug)
            if existing_cap:
                from app.schemas.binding import BindingCapabilityAdd
                await bind_svc.add_capability(
                    record["id"],
                    BindingCapabilityAdd(
                        capability_id=existing_cap["id"],
                        is_enabled=cap_ref.get("is_enabled", True),
                        mount_order=cap_ref.get("mount_order", 0),
                        runtime_overrides=cap_ref.get("runtime_overrides", {}),
                    ),
                )

        return await bind_svc.get_binding(record["id"])
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/import/bundle", status_code=201)
async def import_bundle(file: UploadFile = File(...)):
    """Import a bundle zip file."""
    import zipfile
    import tempfile
    import shutil

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "bundle.zip"
        with open(zip_path, "wb") as f:
            content = await file.read()
            f.write(content)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp)

        results = {"capabilities": [], "bindings": []}

        # Import capabilities
        caps_dir = Path(tmp) / "capabilities"
        if caps_dir.exists():
            for cap_file in caps_dir.glob("*.json"):
                cap_data = json.loads(cap_file.read_text(encoding="utf-8"))
                try:
                    cap = await reg_svc.create_capability(CapabilityCreate(**cap_data))
                    results["capabilities"].append(cap["id"])
                except Exception:
                    pass

        # Import bindings
        binds_dir = Path(tmp) / "bindings"
        if binds_dir.exists():
            for bind_file in binds_dir.glob("*.json"):
                bind_data = json.loads(bind_file.read_text(encoding="utf-8"))
                try:
                    cap_refs = bind_data.pop("capabilities", [])
                    binding = await bind_svc.create_binding(BindingCreate(**bind_data))
                    results["bindings"].append(binding["id"])
                except Exception:
                    pass

        return results


# --- Export ---

@router.get("/export/capability/{cap_id}")
async def export_capability(cap_id: str):
    cap = await reg_svc.get_capability(cap_id)
    if not cap:
        raise HTTPException(404, "Capability not found")

    export_path = exports_dir() / f"capability-{cap['slug']}.json"
    export_path.write_text(json.dumps(cap, indent=2, ensure_ascii=False), encoding="utf-8")
    return FileResponse(export_path, filename=f"capability-{cap['slug']}.json")


@router.get("/export/binding/{binding_id}")
async def export_binding(binding_id: str):
    binding = await bind_svc.get_binding(binding_id)
    if not binding:
        raise HTTPException(404, "Binding not found")

    export_path = exports_dir() / f"binding-{binding['name'].replace(' ', '-')}.json"
    export_path.write_text(json.dumps(binding, indent=2, ensure_ascii=False), encoding="utf-8")
    return FileResponse(export_path, filename=f"binding-{binding['name'].replace(' ', '-')}.json")
