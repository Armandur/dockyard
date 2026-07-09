"""Create-endpoint."""
from fastapi import APIRouter, Depends

from .. import docker_ops
from ..deps import get_docker, rate_limit, require_api_key
from ..schemas import ContainerSpec, CreateResult

router = APIRouter(
    prefix="/containers",
    dependencies=[Depends(require_api_key)],
)


@router.post("", response_model=CreateResult, status_code=201)
def create(spec: ContainerSpec, _rl=Depends(rate_limit), client=Depends(get_docker)):
    """Skapa (och som standard starta) en container + skriv Unraid-template.

    Sync def med flit: docker-SDK:t är blockerande, så FastAPI kör detta i sin
    threadpool i stället för att frysa event-loopen under image-pull.
    """
    return docker_ops.create_container(spec, client)
