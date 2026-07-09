# dockyard

Tunn create-shim för att skapa containrar på Unraid (TERVO2) via ett avgränsat
HTTP-API, i stället för root-SSH eller en öppen Docker-socket.

- **Skapar** containrar via Docker-motorn, bakom en **docker-socket-proxy**
  (minsta rättigheter).
- Skriver en matchande **Unraid-template** (`my-<Namn>.xml`) så containern blir
  förstklassig i GUI:t (ikon, WebUI-länk, update, edit).
- **Create-only.** Start/stopp/update/remove sköts av Unraids inbyggda
  GraphQL-API. Ingen remove-yta här.

## Varför
Unraids GraphQL-API kan styra befintliga containrar men har **ingen
create-mutation**. dockyard fyller luckan med en liten, loggbar och
nyckelskyddad endpoint.

## API
`POST /containers` (header `x-api-key: <API_KEY>`)

```json
{
  "name": "minapp",
  "image": "ghcr.io/armandur/minapp:latest",
  "ports": [{ "container": 8000, "host": 8123, "proto": "tcp" }],
  "volumes": [{ "host": "/mnt/user/appdata/minapp", "container": "/config", "mode": "rw" }],
  "env": { "TZ": "Europe/Stockholm" },
  "webui": "http://[IP]:[PORT:8000]/",
  "autostart": true
}
```

Svar `201`:
```json
{ "ok": true, "name": "minapp", "container_id": "…", "image": "…",
  "state": "running", "template_written": "/templates-user/my-minapp.xml", "warnings": [] }
```

`GET /health` - status + om socket-proxyn svarar (ingen nyckel krävs).

### Guardrails
Shimmen skapar containrar på en host - flera spärrar hindrar att en klient med
giltig nyckel eskalerar till hosten:
- API-nyckel krävs på create (`hmac.compare_digest`).
- **`privileged` är default-nekad** (`ALLOW_PRIVILEGED=true` krävs) - annars ger
  det i praktiken root på hosten.
- **Volymer default-restriktiva:** bara `/mnt/user/` som standard; system-
  kataloger (`/boot`,`/etc`,`/root`,`/proc`,`/sys`,`/var/run`,`/run`,`/dev`) och
  `/` nekas alltid. Styrs av `ALLOWED_VOLUME_PREFIXES` / `DENIED_VOLUME_PREFIXES`.
- **Devices default-deny:** inga får mappas utan `ALLOWED_DEVICE_PREFIXES`.
- `ALLOWED_NAME_PREFIXES` / `ALLOWED_REGISTRIES` (matchas på `/`-gräns) /
  `PROTECTED_NAMES` låser namn och images.
- Vägrar skapa om namnet redan finns (ingen clobbering), även vid race.
- Rate limit på create. Allt stämplas med label `dockyard.managed=true`.

## Lokal dev/test
Kör shimmen + proxy mot VM:ens egna docker (skapar bara testcontainrar):
```bash
cp .env.example .env      # sätt API_KEY
API_KEY=$(openssl rand -hex 32) HOST_PORT=8001 docker compose -f docker-compose.dev.yml up --build
curl -s localhost:8001/health | jq
```

## Deployment på Unraid (Add Container, INTE compose)

Två containrar på ett gemensamt **user-defined bridge-nätverk** (så att shimmen
når proxyn på containernamn). Skapa nätverket en gång:
`docker network create dockyard-net`.

### 1. socket-proxy (`ghcr.io/tecnativa/docker-socket-proxy`)
| Typ | Värde |
|---|---|
| Network | `dockyard-net` |
| Path | `/var/run/docker.sock` → `/var/run/docker.sock` (**ro**) |
| Env `CONTAINERS` | `1` |
| Env `IMAGES` | `1` |
| Env `POST` | `1` |
| Env `INFO` | `1` |
| Env (alla övriga: `NETWORKS`,`VOLUMES`,`EXEC`,`SERVICES`,`SWARM`,`SYSTEM`,`AUTH`,`SECRETS`,`CONFIGS`,`DISTRIBUTION`,`PLUGINS`,`TASKS`,`NODES`) | `0` |

Publicera **ingen** port för proxyn - den ska bara nås internt av shimmen.

### 2. dockyard (`ghcr.io/armandur/dockyard:latest`)
| Typ | Värde |
|---|---|
| Network | `dockyard-net` |
| Port | container `8000` → host `<valfri, t.ex. 8088>` |
| Path | `/mnt/user/appdata/dockyard/templates-user`* → `/templates-user` (**rw**) |
| Env `API_KEY` | `<openssl rand -hex 32>` |
| Env `DOCKER_HOST` | `tcp://socket-proxy:2375` |
| Env `TEMPLATE_DIR` | `/templates-user` |
| Env `WRITE_TEMPLATE` | `true` |
| Env `ALLOWED_REGISTRIES` | t.ex. `ghcr.io/armandur,lscr.io` (valfritt) |
| Env `PROTECTED_NAMES` | t.ex. `plex,frigate,Nginx-Proxy-Manager-Official` (valfritt) |

\* För att templaten ska synas i Unraids GUI ska den hamna i
`/boot/config/plugins/dockerMan/templates-user`. Antingen mappa den vägen direkt
(rw), eller låt en post-hook kopiera dit. Se DOCKER.md om/när det behövs.

> **OBS:** montera `/boot` med försiktighet - det är Unraids USB-config. Enklast
> och säkrast är att mappa exakt `templates-user`-katalogen, inget mer.
