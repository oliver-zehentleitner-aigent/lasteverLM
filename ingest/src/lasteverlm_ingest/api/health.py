from fastapi import APIRouter
from lasteverlm_core import Health

router = APIRouter()


@router.get("/healthz", response_model=Health)
def healthz() -> Health:
    """Liveness plus the build (APP_VERSION, APP_COMMIT) for the admin system view."""
    return Health.from_env()
