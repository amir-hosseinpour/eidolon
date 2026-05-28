from fastapi import Depends, FastAPI

from ..lib.auth import require_bearer
from ..lib.config import Settings
from .routers import engagements, forks, health, tools, vm_agents

settings = Settings()

app = FastAPI(
    title="Eidolon orchestrator",
    version="0.1.0.dev0",
    docs_url="/docs" if settings.debug else None,
)

app.include_router(health.router, prefix="/v1", tags=["health"])
app.include_router(
    engagements.router,
    prefix="/v1/engagements",
    tags=["engagements"],
    dependencies=[Depends(require_bearer)],
)
app.include_router(
    tools.router,
    prefix="/v1/tools",
    tags=["tools"],
    dependencies=[Depends(require_bearer)],
)
app.include_router(
    forks.router,
    prefix="/v1/engagements",
    tags=["forks"],
    dependencies=[Depends(require_bearer)],
)
# VM agent endpoints authenticate via per-VM tokens issued at provision-time,
# NOT the operator bearer token. Do not gate them with require_bearer.
app.include_router(vm_agents.router, prefix="/v1/vm-agent", tags=["vm-agent"])
