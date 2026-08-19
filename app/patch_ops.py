"""Ändra en befintlig container genom att bygga om den.

Docker kan inte ändra env, portar eller volymer på en körande container -
bara resursgränser och restart-policy. Allt annat kräver att containern tas
bort och skapas på nytt. Den ordningen är farlig: går något fel efter
borttagningen står man utan container. Därför valideras och förbereds ALLT
(guardrails, image-pull, den sammanslagna specen) innan den gamla rörs, och
misslyckas skapandet ändå görs ett försök att återställa den gamla specen.
"""
import json
import logging

import docker
from docker.errors import APIError, ImageNotFound, NotFound

from . import config, docker_ops, template
from .docker_ops import SPEC_LABEL, _TRANSPORT_ERRORS
from .errors import DockerBackendError, ForbiddenSpec, NotFoundError, SpecError
from .schemas import ContainerPatch, ContainerSpec, PatchResult, PortMapping, VolumeMapping

log = logging.getLogger("dockyard")

# Labels dockyard sätter själv - de ska inte följa med tillbaka in i specen.
_OWN_LABELS = {
    "dockyard.managed", SPEC_LABEL, "net.unraid.docker.managed",
    "net.unraid.docker.webui", "net.unraid.docker.icon",
}


def _find(name: str, client: docker.DockerClient):
    try:
        containers = client.containers.list(all=True, filters={"name": name})
    except APIError as e:
        raise DockerBackendError(f"Kunde inte slå upp containern: {e}")
    for c in containers:
        if c.name == name:
            return c
    raise NotFoundError(f"Ingen container med namnet '{name}' hittades.")


def _image_defaults(image_ref: str, client: docker.DockerClient) -> tuple[set[str], set[str]]:
    """Image:ns egna env-rader och labels, så de inte förväxlas med användarens.

    Docker slår ihop image-defaults med det som anges vid create, och en
    inspect visar summan. Utan den här filtreringen skulle en ombyggnad
    permanenta imagens defaults som om användaren hade satt dem.
    """
    try:
        image = client.images.get(image_ref)
    except (ImageNotFound, NotFound, APIError):
        return set(), set()
    cfg = image.attrs.get("Config", {}) or {}
    return set(cfg.get("Env") or []), set((cfg.get("Labels") or {}).keys())


def _derive_spec(container, client: docker.DockerClient) -> tuple[ContainerSpec, list[str]]:
    """Härled en spec ur en container som saknar spec-label.

    Gäller containrar skapade före spec-labeln fanns. Template-metadata
    (overview, project, category) går inte att läsa ur containern - den
    informationen finns bara i template-XML:en och går förlorad.
    """
    attrs = container.attrs
    cfg = attrs.get("Config") or {}
    host = attrs.get("HostConfig") or {}
    warnings = ["Containern saknar dockyard-spec: portar, volymer och env lästes "
                "ur den körande containern, och template-metadata (overview, "
                "project, category) kunde inte återskapas."]

    env_defaults, label_defaults = _image_defaults(cfg.get("Image", ""), client)
    env = {}
    for row in cfg.get("Env") or []:
        if row in env_defaults or "=" not in row:
            continue
        key, _, value = row.partition("=")
        env[key] = value

    ports = []
    for spec_key, bindings in (host.get("PortBindings") or {}).items():
        port, _, proto = spec_key.partition("/")
        for binding in bindings or []:
            host_port = binding.get("HostPort")
            if host_port:
                ports.append(PortMapping(container=int(port), host=int(host_port),
                                         proto=proto or "tcp"))

    volumes = []
    for bind in host.get("Binds") or []:
        parts = bind.split(":")
        if len(parts) >= 2:
            volumes.append(VolumeMapping(host=parts[0], container=parts[1],
                                         mode=parts[2] if len(parts) > 2 else "rw"))

    labels = {
        k: v for k, v in (cfg.get("Labels") or {}).items()
        if k not in _OWN_LABELS and k not in label_defaults
    }
    devices = [
        f"{d.get('PathOnHost')}:{d.get('PathInContainer')}:{d.get('CgroupPermissions', 'rwm')}"
        for d in (host.get("Devices") or [])
    ]

    spec = ContainerSpec(
        name=container.name,
        image=cfg.get("Image") or "",
        network=host.get("NetworkMode") or "bridge",
        restart=(host.get("RestartPolicy") or {}).get("Name") or None,
        privileged=bool(host.get("Privileged")),
        ports=ports,
        volumes=volumes,
        env=env,
        labels=labels,
        devices=devices,
        webui=(cfg.get("Labels") or {}).get("net.unraid.docker.webui"),
        icon=(cfg.get("Labels") or {}).get("net.unraid.docker.icon"),
    )
    return spec, warnings


def current_spec(container, client: docker.DockerClient) -> tuple[ContainerSpec, list[str]]:
    raw = (container.attrs.get("Config", {}).get("Labels") or {}).get(SPEC_LABEL)
    if not raw:
        return _derive_spec(container, client)
    try:
        spec = ContainerSpec(**json.loads(raw))
    except (ValueError, TypeError) as exc:
        log.warning("Trasig spec-label på %s: %s", container.name, exc)
        spec, warnings = _derive_spec(container, client)
        return spec, warnings + [f"Spec-labeln gick inte att läsa ({exc})."]
    return spec, []


def merge(spec: ContainerSpec, patch: ContainerPatch) -> ContainerSpec:
    """Slår ihop patchen med nuvarande spec. env läggs till, listor ersätts."""
    data = spec.model_dump()

    env = dict(data.get("env") or {})
    if patch.env:
        env.update(patch.env)
    for key in patch.env_remove:
        env.pop(key, None)
    data["env"] = env

    for field in ("image", "network", "restart", "privileged", "webui", "icon",
                  "overview", "support", "project", "category", "autostart"):
        value = getattr(patch, field)
        if value is not None:
            data[field] = value

    for field in ("ports", "volumes", "labels", "devices"):
        value = getattr(patch, field)
        if value is not None:
            data[field] = [v.model_dump() if hasattr(v, "model_dump") else v
                           for v in value] if isinstance(value, list) else value

    return ContainerSpec(**data)


def _check_patchable(container, name: str) -> None:
    """Bara containrar dockyard själv skapat får byggas om.

    En ombyggnad tar bort containern på riktigt. Att låta det gälla vad som
    helst på hosten vore en raderingsprimitiv förklädd till en uppdatering.
    """
    if name in config.PROTECTED_NAMES:
        raise ForbiddenSpec(f"Namnet '{name}' är skyddat och får inte ändras.")
    labels = container.attrs.get("Config", {}).get("Labels") or {}
    if labels.get(config.MANAGED_LABEL) != "true":
        raise ForbiddenSpec(
            f"Containern '{name}' är inte skapad av dockyard och byggs inte om. "
            "Ombyggnaden tar bort och återskapar containern, och det görs bara "
            "på containrar dockyard äger."
        )


def _create_and_start(spec: ContainerSpec, client: docker.DockerClient):
    """Skapar containern och startar den. Returnerar (container, warnings).

    Start-felet hålls isär från create-felet med flit: Docker validerar host-
    portbindningar först vid start, så en upptagen port ger en container som
    finns men inte kör. Läcker det felet uppåt försöker anroparen "återställa"
    under ett namn som redan är taget, och rapporterar att containern är borta
    fast den står där.
    """
    container = client.containers.create(
        image=spec.image,
        name=spec.name,
        detach=True,
        network=spec.network,
        ports=docker_ops._ports(spec),
        volumes=docker_ops._volumes(spec),
        environment=spec.env,
        labels=docker_ops._labels(spec),
        devices=spec.devices,
        privileged=spec.privileged,
        restart_policy={"Name": spec.restart or config.DEFAULT_RESTART},
    )
    warnings: list[str] = []
    if spec.autostart:
        try:
            container.start()
        except (APIError, *_TRANSPORT_ERRORS) as e:
            warnings.append(f"Containern byggdes om men kunde inte startas: {e}")
    return container, warnings


def patch_container(name: str, patch: ContainerPatch,
                    client: docker.DockerClient) -> PatchResult:
    container = _find(name, client)
    _check_patchable(container, name)

    spec, warnings = current_spec(container, client)
    was_running = container.status == "running"
    if patch.autostart is None:
        spec.autostart = was_running

    new_spec = merge(spec, patch)
    changed = patch.changed_fields()
    if not changed:
        raise SpecError("Patchen innehöll inga fält att ändra.")

    # Allt som kan neka ändringen ska göra det INNAN den gamla containern rörs.
    docker_ops._check_guardrails_for_patch(new_spec)

    # Pulla BARA när image:n faktiskt byts. En env-ändring ska inte dra ner
    # en ny latest och uppgradera containern i smyg - och för ett privat
    # registry skulle pullen dessutom faila fast imagen redan finns lokalt.
    if patch.image is not None and patch.image != spec.image:
        repo, tag = docker_ops._split_ref(new_spec.image)
        log.info("Pullar image %s:%s inför ombyggnad av %s", repo, tag, name)
        try:
            client.images.pull(repo, tag=tag)
        except (ImageNotFound, NotFound):
            raise DockerBackendError(f"Image hittades inte: {new_spec.image}")
        except (APIError, *_TRANSPORT_ERRORS) as e:
            raise DockerBackendError(f"Kunde inte pulla image {new_spec.image}: {e}")
    else:
        # Imagen måste finnas lokalt, annars går containern inte att skapa igen.
        try:
            client.images.get(new_spec.image)
        except (ImageNotFound, NotFound):
            raise DockerBackendError(
                f"Image {new_spec.image} finns inte lokalt. Skicka med \"image\" "
                "i patchen för att hämta den."
            )
        except (APIError, *_TRANSPORT_ERRORS) as e:
            raise DockerBackendError(f"Kunde inte slå upp image {new_spec.image}: {e}")

    log.info("Bygger om %s (ändrat: %s)", name, ", ".join(changed))
    try:
        container.remove(force=True)
    except (APIError, *_TRANSPORT_ERRORS) as e:
        raise DockerBackendError(
            f"Kunde inte ta bort den gamla containern, inget ändrades: {e}"
        )

    try:
        new_container, start_warnings = _create_and_start(new_spec, client)
        warnings.extend(start_warnings)
    except (APIError, *_TRANSPORT_ERRORS) as e:
        # Den gamla är borta. Försök sätta tillbaka den så hosten inte blir
        # stående utan tjänst på grund av en avvisad ändring.
        try:
            _create_and_start(spec, client)
            raise DockerBackendError(
                f"Den nya containern kunde inte skapas ({e}). Den gamla "
                "konfigurationen är återställd."
            )
        except (APIError, *_TRANSPORT_ERRORS) as restore_error:
            raise DockerBackendError(
                f"Den nya containern kunde inte skapas ({e}) och återställningen "
                f"misslyckades också ({restore_error}). Containern '{name}' finns "
                "inte längre och måste skapas om manuellt."
            )

    try:
        new_container.reload()
        state = new_container.status
    except APIError:
        state = "unknown"

    template_written = None
    if config.WRITE_TEMPLATE:
        try:
            template_written = template.write(new_spec)
        except OSError as e:
            warnings.append(f"Container ombyggd men template-XML kunde inte skrivas: {e}")

    return PatchResult(
        ok=True,
        name=name,
        container_id=new_container.id,
        image=new_spec.image,
        state=state,
        changed=changed,
        recreated=True,
        template_written=template_written,
        warnings=warnings,
    )
