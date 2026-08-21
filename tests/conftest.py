"""Testrigg: API-nyckel satt före app-import, fejkad docker-klient.

Dockyard pratar med en docker-socket-proxy i drift. Testerna ska aldrig röra
en riktig docker, så get_docker-beroendet överlagras med en fejk som svarar
på de filter routes faktiskt använder (name-uppslag och label-filtrering).
"""
import json
import os

os.environ.setdefault("API_KEY", "testnyckel")
os.environ.setdefault("DOCKER_HOST", "tcp://127.0.0.1:1")  # rörs aldrig

import pytest
from fastapi.testclient import TestClient

from app.deps import get_docker
from app.main import app

API_KEY = os.environ["API_KEY"]


class _FakeImage:
    tags = ["ghcr.io/armandur/minapp:v2"]


class FakeContainer:
    def __init__(self, name, labels, status="running", image="ghcr.io/armandur/minapp:v2"):
        self.name = name
        self.status = status
        self.image = _FakeImage()
        self.attrs = {"Config": {"Labels": labels, "Image": image}}


def managed_container():
    """En container med dockyard-labels och en giltig spec-label att läsa tillbaka."""
    spec = {
        "name": "minapp",
        "image": "ghcr.io/armandur/minapp:v2",
        "ports": [{"container": 8000, "host": 8123, "proto": "tcp"}],
        "env": {"TZ": "Europe/Stockholm", "SECRET": "hemlig"},
    }
    return FakeContainer(
        "minapp",
        {"dockyard.managed": "true", "dockyard.spec": json.dumps(spec)},
    )


class FakeContainers:
    def __init__(self, containers):
        self._all = containers

    def list(self, all=False, filters=None):
        filters = filters or {}
        if "name" in filters:
            return [c for c in self._all if c.name == filters["name"]]
        if filters.get("label") == "dockyard.managed=true":
            return [c for c in self._all if c.attrs["Config"]["Labels"].get("dockyard.managed") == "true"]
        return list(self._all)


class FakeClient:
    def __init__(self, containers):
        self.containers = FakeContainers(containers)


@pytest.fixture
def client():
    """TestClient där get_docker ger en fejk med en managed och en främmande container."""
    fake = FakeClient([managed_container(), FakeContainer("plex", {})])
    app.dependency_overrides[get_docker] = lambda: fake
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def auth():
    return {"x-api-key": API_KEY}
