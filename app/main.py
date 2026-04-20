from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.core.config import settings
from app.core.db import init_db, close_db
from app.core.logging import setup_logging
from app.core.paths import ensure_data_dirs
from app.core.seed_data import ensure_skill_seed_files, seed_default_capabilities


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    ensure_data_dirs()
    ensure_skill_seed_files()
    await init_db()
    await seed_default_capabilities(prune_missing=True)
    yield
    await close_db()


app = FastAPI(
    title="MCP Shelf",
    description="MCP / Tool / Skill Registry + Binding Config + Playground",
    version="0.1.0",
    lifespan=lifespan,
    root_path=settings.root_path,
)

# Static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Routers - will be included after they are implemented
from app.routers import capabilities as cap_router  # noqa: E402
from app.routers import bindings as bind_router  # noqa: E402
from app.routers import sessions as sess_router  # noqa: E402
from app.routers import runtime as rt_router  # noqa: E402
from app.routers import pages as page_router  # noqa: E402
from app.routers import health as health_router  # noqa: E402
from app.routers import audit as audit_router  # noqa: E402
from app.routers import import_export as ie_router  # noqa: E402
from app.routers import llm_configs as llm_router  # noqa: E402
from app.routers import backup as backup_router  # noqa: E402
from app.routers import skills as skills_router  # noqa: E402

app.include_router(page_router.router)
app.include_router(cap_router.router, prefix="/api/capabilities", tags=["capabilities"])
app.include_router(bind_router.router, prefix="/api/bindings", tags=["bindings"])
app.include_router(sess_router.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(rt_router.router, prefix="/api/sessions", tags=["runtime"])
app.include_router(health_router.router, prefix="/api/health", tags=["health"])
app.include_router(audit_router.router, prefix="/api/audit", tags=["audit"])
app.include_router(ie_router.router, prefix="/api", tags=["import-export"])
app.include_router(llm_router.router, prefix="/api/llm-configs", tags=["llm-configs"])
app.include_router(backup_router.router, prefix="/api", tags=["backup"])
app.include_router(skills_router.router, prefix="/api/skills", tags=["skills"])


def cli():
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    cli()
