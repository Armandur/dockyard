"""Endpoints för att skapa och ändra containrar."""
from fastapi import APIRouter, Depends

from .. import docker_ops, patch_ops
from ..deps import get_docker, rate_limit, require_api_key
from ..schemas import ContainerPatch, ContainerSpec, CreateResult, PatchResult

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


@router.patch("/{name}", response_model=PatchResult)
def patch(name: str, patch: ContainerPatch, _rl=Depends(rate_limit),
          client=Depends(get_docker)):
    """Ändra en befintlig container genom att bygga om den.

    Docker kan inte ändra env, portar eller volymer i efterhand, så containern
    tas bort och skapas på nytt med den sammanslagna specen. Bind-monterade
    volymer ligger kvar på hosten och följer med. Gäller bara containrar
    dockyard själv skapat. Sync def av samma skäl som create.
    """
    return patch_ops.patch_container(name, patch, client)
