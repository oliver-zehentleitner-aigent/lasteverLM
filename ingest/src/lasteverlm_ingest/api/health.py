from fastapi import APIRouter, Request
from lasteverlm_core import Health
from lasteverlm_core.health import DependencyProbe

router = APIRouter()


@router.get("/healthz", response_model=Health)
async def healthz(request: Request) -> Health:
    """Liveness plus the build (APP_VERSION, APP_COMMIT) and the state of
    the database, the bucket and the inference API for the admin system
    view; `status` stays "ok" while a dependency is down."""
    probe: DependencyProbe = request.app.state.dependency_probe
    return Health.from_env(dependencies=await probe.states())
