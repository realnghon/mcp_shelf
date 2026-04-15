"""Seed marketplace data into SQLite."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.db import init_db
from app.services.registry_service import RegistryService
from app.services.binding_service import BindingService
from app.schemas.capability import CapabilityCreate
from app.schemas.binding import BindingCreate, BindingCapabilityAdd
from app.core.paths import marketplace_capabilities_dir, marketplace_bindings_dir


async def seed_capabilities(svc: RegistryService):
    cap_dir = marketplace_capabilities_dir()
    for f in sorted(cap_dir.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        existing = await svc.get_by_slug(data["slug"])
        if existing:
            print(f"  Skip (exists): {data['slug']}")
            continue
        cap = CapabilityCreate(**data)
        record = await svc.create_capability(cap)
        print(f"  Created: {record['name']} ({record['id'][:8]})")


async def seed_bindings(bind_svc: BindingService, reg_svc: RegistryService):
    bind_dir = marketplace_bindings_dir()
    for f in sorted(bind_dir.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        cap_refs = data.pop("capabilities", [])
        binding = BindingCreate(**data)
        record = await bind_svc.create_binding(binding)
        print(f"  Created: {record['name']} ({record['id'][:8]})")

        for cap_ref in cap_refs:
            slug = cap_ref.get("slug", "")
            cap = await reg_svc.get_by_slug(slug)
            if cap:
                await bind_svc.add_capability(
                    record["id"],
                    BindingCapabilityAdd(
                        capability_id=cap["id"],
                        is_enabled=cap_ref.get("is_enabled", True),
                        mount_order=cap_ref.get("mount_order", 0),
                        runtime_overrides=cap_ref.get("runtime_overrides", {}),
                    ),
                )
                print(f"    Attached: {slug}")
            else:
                print(f"    Skip (not found): {slug}")


async def main():
    print("Initializing database...")
    await init_db()

    reg_svc = RegistryService()
    bind_svc = BindingService()

    print("\nSeeding capabilities:")
    await seed_capabilities(reg_svc)

    print("\nSeeding bindings:")
    await seed_bindings(bind_svc, reg_svc)

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
