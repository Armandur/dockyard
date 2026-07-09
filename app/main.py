"""dockyard - tunn create-shim för containrar på Unraid.

Skapar containrar via Docker-motorn (bakom en socket-proxy) och skriver en
matchande Unraid-template så de blir förstklassiga i GUI:t. Create-only.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import config, docker_ops
from .deps import get_docker
from .errors import DockyardError
from .routes import containers, health

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("dockyard")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.validate()
    if docker_ops.ping(get_docker()):
        log.info("Docker nås via %s", config.DOCKER_HOST)
    else:
        log.warning("Docker svarar INTE på %s (proxy nere?) - startar ändå", config.DOCKER_HOST)
    yield


app = FastAPI(title="dockyard", version="0.1.0", lifespan=lifespan)


@app.exception_handler(DockyardError)
async def _dockyard_error(request: Request, exc: DockyardError):
    return JSONResponse(status_code=exc.status_code, content={"ok": False, "error": exc.message})


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    # Fångar allt oväntat (t.ex. transportfel) och svarar med samma JSON-kuvert
    # som resten av API:t - utan att läcka interna detaljer till klienten.
    log.exception("Ohanterat fel på %s", request.url.path)
    return JSONResponse(status_code=500, content={"ok": False, "error": "Internt fel."})


app.include_router(health.router)
app.include_router(containers.router)
