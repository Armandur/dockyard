"""Route-prov för GET /containers och GET /containers/{name} (TASK-1453).

Proven anropar ROUTEN, inte bara patch_ops - så auth-spärren (401),
ägarspärren (403) och 404 fångas, inte bara den lyckade läsningen.
"""
from app.schemas import ContainerSpec


def test_las_spec_round_trippar(client, auth):
    r = client.get("/containers/minapp", headers=auth)
    assert r.status_code == 200
    spec = r.json()
    # svaret ska gå att skicka tillbaka som en giltig POST/PATCH-spec
    ContainerSpec(**spec)
    assert spec["env"]["TZ"] == "Europe/Stockholm"
    assert spec["ports"] == [{"container": 8000, "host": 8123, "proto": "tcp"}]


def test_las_ger_env_i_klartext(client, auth):
    # medvetet val: anroparen har redan full kontroll via samma nyckel, och
    # round-trip kräver att nuvarande env syns. Faller provet är beslutet ändrat.
    r = client.get("/containers/minapp", headers=auth)
    assert r.json()["env"]["SECRET"] == "hemlig"


def test_las_frammande_container_ger_403(client, auth):
    r = client.get("/containers/plex", headers=auth)
    assert r.status_code == 403
    assert "inte skapad av dockyard" in r.json()["error"]


def test_las_okand_container_ger_404(client, auth):
    r = client.get("/containers/saknas", headers=auth)
    assert r.status_code == 404


def test_las_utan_nyckel_ger_401(client):
    r = client.get("/containers/minapp")
    assert r.status_code == 401


def test_lista_bara_managed(client, auth):
    r = client.get("/containers", headers=auth)
    assert r.status_code == 200
    namn = [c["name"] for c in r.json()]
    assert namn == ["minapp"]  # plex (utan managed-label) ska inte synas


def test_lista_utan_nyckel_ger_401(client):
    r = client.get("/containers")
    assert r.status_code == 401
