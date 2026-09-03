"""Endpoints för att skapa, läsa, ändra och starta containrar."""
from fastapi import APIRouter, Depends

from .. import docker_ops, patch_ops
from ..deps import get_docker, rate_limit, require_api_key
from ..schemas import (
    ContainerPatch,
    ContainerSpec,
    ContainerSummary,
    CreateResult,
    PatchResult,
    StartResult,
)

router = APIRouter(
    prefix="/containers",
    dependencies=[Depends(require_api_key)],
)


@router.get("", response_model=list[ContainerSummary])
def lista(client=Depends(get_docker)):
    """Lista de containrar dockyard hanterar (managed-label)."""
    return patch_ops.list_managed(client)


@router.get("/{name}", response_model=ContainerSpec)
def las(name: str, client=Depends(get_docker)):
    """Läs ut en dockyard-containers spec i POST/PATCH-form (round-trip).

    Gäller bara containrar dockyard äger - annars 403, så endpointen inte blir
    ett sätt att läsa env ur vilken container som helst. env returneras i
    klartext med flit; se read_spec.
    """
    return patch_ops.read_spec(name, client)


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


@router.post("/{name}/start", response_model=StartResult)
def start(name: str, _rl=Depends(rate_limit), client=Depends(get_docker)):
    """Starta en stoppad dockyard-ägd container.

    Anropet är idempotent: en container som redan kör lämnas orörd. Sync def
    med flit eftersom docker-SDK:t är blockerande och ska köras i threadpool.
    """
    return patch_ops.start_container(name, client)
