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
async def create(spec: ContainerSpec, _rl=Depends(rate_limit), client=Depends(get_docker)):
    """Skapa (och som standard starta) en container + skriv Unraid-template."""
    return docker_ops.create_container(spec, client)
