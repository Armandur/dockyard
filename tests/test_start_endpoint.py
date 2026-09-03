"""Route-prov för POST /containers/{name}/start (TASK-1565)."""
import pytest
from fastapi.testclient import TestClient

from app.deps import get_docker
from app.main import app
from conftest import API_KEY, FakeClient, FakeContainer


class StartableContainer(FakeContainer):
    def __init__(self, name, labels, status="exited"):
        super().__init__(name, labels, status=status)
        self.start_calls = 0
        self.reload_calls = 0

    def start(self):
        self.start_calls += 1
        self.status = "running"

    def reload(self):
        self.reload_calls += 1


@pytest.fixture
def start_client():
    stopped = StartableContainer(
        "stoppad", {"dockyard.managed": "true"}, status="exited"
    )
    running = StartableContainer(
        "kor", {"dockyard.managed": "true"}, status="running"
    )
    foreign = StartableContainer("plex", {}, status="exited")
    fake = FakeClient([stopped, running, foreign])
    app.dependency_overrides[get_docker] = lambda: fake
    yield TestClient(app), stopped, running
    app.dependency_overrides.clear()


def test_startar_stoppad_container(start_client):
    client, stopped, _ = start_client
    response = client.post(
        "/containers/stoppad/start", headers={"x-api-key": API_KEY}
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "name": "stoppad", "state": "running"}
    assert stopped.start_calls == 1
    assert stopped.reload_calls == 1


def test_redan_korande_ar_idempotent(start_client):
    client, _, running = start_client
    response = client.post("/containers/kor/start", headers={"x-api-key": API_KEY})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "name": "kor", "state": "running"}
    assert running.start_calls == 0
    assert running.reload_calls == 0


def test_frammande_container_ger_403(start_client):
    client, _, _ = start_client
    response = client.post("/containers/plex/start", headers={"x-api-key": API_KEY})

    assert response.status_code == 403
    assert "inte skapad av dockyard" in response.json()["error"]


def test_okand_container_ger_404(start_client):
    client, _, _ = start_client
    response = client.post(
        "/containers/saknas/start", headers={"x-api-key": API_KEY}
    )

    assert response.status_code == 404


def test_utan_nyckel_ger_401(start_client):
    client, _, _ = start_client
    response = client.post("/containers/stoppad/start")

    assert response.status_code == 401
