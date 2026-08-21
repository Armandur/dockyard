# Backlog Export

## [P2][done] [dockyard] Stöd att ÄNDRA befintliga containrar (inte bara skapa)

Dockyard är idag create-only. Att ändra en containers env/portar/volymer (t.ex. BIRDNET_UID/GID 1000->99, en portmappning, en ny volym) kräver att man tar bort och skapar om containern via Unraid-GraphQL + dockyard. Lägg en update/patch-endpoint (PATCH /containers/{name}?) som ändrar en befintlig container (recreate-under-huven med bevarade volymer, eller in-place dar det gar) sa vanliga andringar blir en operation. Konkret smärta: BirdNET-Go i duharfagel-projektet fick permission-krasch nar appdata-agarskapet aterstalldes till 99:100 av Unraids permission-verktyg; att byta UID kravde full remove+recreate. Samma guardrails som create (registry/volym/namn).

- ID: `01KXZ2EK1PHQN5Q5BGYV9DF2YC`
- Type: feature
- Actor: ai:claude-code

---

## [P3][done] [dockyard] GET-endpoint som läser ut en containers spec

Det går att skapa (POST) och ändra (PATCH) en container, men inte att LÄSA vad den har för spec i dag. Det gör PATCH svårare att använda än det borde vara, eftersom ports, volumes, labels och devices ERSÄTTER hela listan - man måste alltså redan känna till hela uppsättningen för att kunna lägga till en enda volym utan att tappa de andra.

Upptäckt 2026-08-21 när flipp-dl-dev:s /output skulle pekas om: GET $DOCKYARD_URL/containers/<namn> svarar "Method Not Allowed". Enda vägen till nuvarande mountar var Unraids GraphQL-API (docker { containers { mounts } }), som svarar med Dockers råa form (Source/Destination/Mode) och inte dockyards egen (host/container/mode).

Att göra:
- GET /containers/<namn> som returnerar specen i samma form som POST/PATCH tar emot, så svaret kan modifieras och skickas tillbaka rakt av.
- Rimligen även GET /containers som listar de containrar dockyard hanterar.
- Samma auth och guardrails som resten. En container dockyard inte skapat bör ge 403, precis som PATCH gör - annars blir endpointen ett sätt att läsa ut env-variabler (och därmed hemligheter) ur vilken container som helst på servern.
- Fundera på om env ska maskeras eller utelämnas i svaret av samma skäl.

- ID: `01M0JV7NZZCNZY41DQ5FFMJ9PH`
- Type: feature
- Actor: ai:claude-code

---

## [P3][todo] [dockyard] Stöd privata registry-credentials vid image-pull

Upptäckt under Chicago TASK-382. Dockyard använder docker-py client.images.pull utan auth_config och ser inte Unraid-hostens docker login eftersom klienten kör inuti dockyard-containern. Lägg ett säkert konfigurerbart registry-authflöde utan att logga tokens, dokumentera secret-mount/env och testa pull från privat GHCR. Klart när create-endpointen kan pulla en privat ghcr.io/armandur-image och inga credentials skrivs i API-svar eller logg.

- ID: `01KZVKPVRX09QNPY1YZ63FNTDX`
- Type: improvement
- Actor: ai:codex

---

