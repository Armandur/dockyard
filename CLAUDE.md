# dockyard - kodbasbeskrivning för Claude

Tunn FastAPI-shim som skapar containrar på Unraid (TERVO2) via Docker-motorn
bakom en docker-socket-proxy, och skriver matchande Unraid-template-XML.
Create-only; livscykel sköts av Unraids GraphQL-API.

## Stack
- Python 3.12 + FastAPI (uvicorn)
- `docker` (Python SDK) mot `tcp://socket-proxy:2375`
- Jinja2 för template-XML
- Deploy: Docker, image `ghcr.io/armandur/dockyard`, Add Container på Unraid
- Config: `.env` (python-dotenv)

## Filstruktur
```
app/
  main.py            # app, lifespan (validate + docker-ping), exception handler, routers
  config.py          # env-config + guardrail-inställningar + validate()
  deps.py            # get_docker, require_api_key, rate_limit  (importeras härifrån)
  schemas.py         # ContainerSpec, PortMapping, VolumeMapping, CreateResult
  errors.py          # DockyardError-hierarki (status_code + svenskt meddelande)
  docker_ops.py      # create_container(): guardrails -> pull -> create -> start -> template
  template.py        # render/write Unraid-XML från spec
  templates/
    unraid_container.xml.j2
  routes/
    health.py        # GET /health (docker-ping)
    containers.py    # POST /containers (create, nyckelskyddad + rate limit)
```

## Designbeslut
- **Aldrig docker.sock direkt** - alltid via socket-proxy med minsta scope
  (CONTAINERS+IMAGES+POST+INFO). Byt inte till direkt socket utan att fråga.
- **Förstklassig i Unraid**: matchande `my-<Name>.xml` i templates-user +
  label `net.unraid.docker.managed=dockerman` gör att GUI:t associerar den
  körande containern med en template (ikon/WebUI/update/edit).
- **Create-only** medvetet - remove/stop hålls utanför för minimal attackyta.
- **Fail-closed**: `config.validate()` kräver API_KEY (>=16 tecken) vid start.
- Guardrails: `ALLOWED_NAME_PREFIXES`, `ALLOWED_REGISTRIES`, `PROTECTED_NAMES`,
  namnkrock-koll, rate limit.

## Miljövariabler
Se `.env.example`. Nyckelvariabler: `API_KEY`, `DOCKER_HOST`, `TEMPLATE_DIR`,
`WRITE_TEMPLATE`, `ALLOWED_NAME_PREFIXES`, `ALLOWED_REGISTRIES`, `PROTECTED_NAMES`.

## Vanliga ändringar
- Nytt fält i spec: `schemas.py` -> mappa i `docker_ops.py` (create-kwargs) ->
  ev. `template._configs()` för att synas i GUI.
- Ny guardrail: `config.py` + `docker_ops._check_guardrails`.

## Verifiering efter ändring
```bash
uv run python -c "from app.main import app; print('OK')"
uv run python -c "from jinja2 import Environment, FileSystemLoader as F; \
  Environment(loader=F('app/templates')).get_template('unraid_container.xml.j2'); print('OK')"
```
Lokalt end-to-end: `docker compose -f docker-compose.dev.yml up --build` och
`POST /containers` med ett `dockyard-test-`-namn.

## Status
v0.1.0 - create + template + guardrails klart. Ej driftsatt på TERVO2 än.
Kvarstår: DOCKER.md för template-katalog-mappningen, ev. dry-run-läge.
