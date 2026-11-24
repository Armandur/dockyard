import json
from collections import deque
from unittest.mock import Mock
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient

from app import config, deps
from app.main import app
from conftest import managed_container

IMAGE = "ghcr.io/rufftruffles/stash-nvenc-patches"


@pytest.fixture
def docker_api(monkeypatch, tmp_path):
    backend = Mock()
    backend.info.return_value = {"Runtimes": {"runc": {}, "nvidia": {}}}
    backend.containers.list.return_value = []
    backend.containers.create.return_value = Mock(id="ny-container", status="running")
    backend.images.get.return_value = Mock(attrs={})
    monkeypatch.setitem(app.dependency_overrides, deps.get_docker, lambda: backend)
    monkeypatch.setattr(deps, "_calls", deque())
    monkeypatch.setattr(config, "ALLOWED_REGISTRIES", [IMAGE, "ghcr.io/armandur"])
    monkeypatch.setattr(config, "ALLOWED_RUNTIMES", set())
    monkeypatch.setattr(config, "WRITE_TEMPLATE", True)
    monkeypatch.setattr(config, "TEMPLATE_DIR", str(tmp_path))
    return TestClient(app), backend


def test_skapa_med_nvidia_runtime(docker_api, auth, monkeypatch):
    client, backend = docker_api
    monkeypatch.setattr(config, "ALLOWED_RUNTIMES", {"nvidia"})
    response = client.post("/containers", headers=auth, json={
        "name": "stash-test", "image": f"{IMAGE}:v0.32.0-test", "runtime": "nvidia",
    })
    assert response.status_code == 201, response.text
    backend.images.pull.assert_called_once_with(IMAGE, tag="v0.32.0-test")
    options = backend.containers.create.call_args.kwargs
    assert options["runtime"] == "nvidia"
    assert json.loads(options["labels"]["dockyard.spec"])["runtime"] == "nvidia"
    template = ElementTree.parse(response.json()["template_written"])
    assert template.findtext("ExtraParams") == "--runtime=nvidia"


@pytest.mark.parametrize(("runtime", "status"), [("nvidia", 403), ("nvidia runc", 422)])
def test_otillaten_runtime_stoppar_create(docker_api, auth, runtime, status):
    client, backend = docker_api
    response = client.post("/containers", headers=auth, json={
        "name": "stash-test", "image": f"{IMAGE}:test", "runtime": runtime,
    })
    assert response.status_code == status, response.text
    backend.images.pull.assert_not_called()
    backend.containers.create.assert_not_called()


def test_repo_med_samma_prefix_nekas(docker_api, auth):
    client, backend = docker_api
    response = client.post("/containers", headers=auth, json={
        "name": "stash-test", "image": f"{IMAGE}-annat:test",
    })
    assert response.status_code == 403, response.text
    backend.images.pull.assert_not_called()


def test_skapa_utan_runtime_anvander_dockers_standard(docker_api, auth):
    client, backend = docker_api
    response = client.post("/containers", headers=auth, json={
        "name": "stash-test", "image": f"{IMAGE}:test",
    })
    assert response.status_code == 201, response.text
    assert backend.containers.create.call_args.kwargs["runtime"] is None
    backend.info.assert_not_called()
    template = ElementTree.parse(response.json()["template_written"])
    assert template.findtext("ExtraParams") == ""


def test_patch_behaller_inspekterad_runtime(docker_api, auth, monkeypatch):
    client, backend = docker_api
    monkeypatch.setattr(config, "ALLOWED_RUNTIMES", {"nvidia"})
    old = managed_container()
    old.attrs["Config"]["Labels"].pop("dockyard.spec")
    old.attrs["HostConfig"] = {"Runtime": "nvidia"}
    old.remove = Mock()
    backend.containers.list.return_value = [old]

    read = client.get("/containers/minapp", headers=auth)
    assert read.json()["runtime"] == "nvidia"
    response = client.patch("/containers/minapp", headers=auth, json={"env": {"TEST": "ja"}})
    assert response.status_code == 200, response.text
    old.remove.assert_called_once_with(force=True)
    assert backend.containers.create.call_args.kwargs["runtime"] == "nvidia"


def test_saknad_runtime_stoppar_patch_fore_ombyggnad(docker_api, auth, monkeypatch):
    client, backend = docker_api
    monkeypatch.setattr(config, "ALLOWED_RUNTIMES", {"nvidia"})
    backend.info.return_value = {"Runtimes": {"runc": {}}}
    old = managed_container()
    old.remove = Mock()
    backend.containers.list.return_value = [old]

    response = client.patch("/containers/minapp", headers=auth, json={"runtime": "nvidia"})
    assert response.status_code == 502, response.text
    assert "saknar runtime 'nvidia'" in response.json()["error"]
    old.remove.assert_not_called()
    backend.containers.create.assert_not_called()
