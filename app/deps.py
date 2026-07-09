"""FastAPI-dependencies: auth, rate limit, docker-klient.

Importeras härifrån av route-filerna - definiera aldrig lokala kopior.
"""
import hmac
import time
from collections import deque

import docker
from fastapi import Header, HTTPException

from . import config

_client: docker.DockerClient | None = None
_calls: deque[float] = deque()


def get_docker() -> docker.DockerClient:
    """Delad docker-klient mot socket-proxyn."""
    global _client
    if _client is None:
        _client = docker.DockerClient(
            base_url=config.DOCKER_HOST, timeout=config.DOCKER_TIMEOUT
        )
    return _client


async def require_api_key(x_api_key: str = Header(default="")) -> None:
    if not hmac.compare_digest(x_api_key, config.API_KEY):
        raise HTTPException(status_code=401, detail="Ogiltig eller saknad API-nyckel.")


async def rate_limit() -> None:
    now = time.monotonic()
    window = config.RATELIMIT_WINDOW_S
    while _calls and _calls[0] < now - window:
        _calls.popleft()
    if len(_calls) >= config.RATELIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail=f"För många anrop - max {config.RATELIMIT_MAX} per {window} s.",
        )
    _calls.append(now)
