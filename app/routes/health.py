"""Hälsokontroll - inkl. att socket-proxyn svarar."""
from fastapi import APIRouter, Depends

from .. import config, docker_ops
from ..deps import get_docker

router = APIRouter()


@router.get("/health")
async def health(client=Depends(get_docker)):
    docker_ok = docker_ops.ping(client)
    return {
        "status": "ok" if docker_ok else "degraded",
        "docker": docker_ok,
        "docker_host": config.DOCKER_HOST,
        "write_template": config.WRITE_TEMPLATE,
        "template_dir": config.TEMPLATE_DIR if config.WRITE_TEMPLATE else None,
    }
