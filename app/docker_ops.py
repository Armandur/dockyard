"""Skapa-logik mot Docker-motorn (via socket-proxyn)."""
import logging

import docker
import requests
from docker.errors import APIError, ImageNotFound, NotFound

from . import config, template
from .errors import ConflictError, DockerBackendError, ForbiddenSpec
from .schemas import ContainerSpec, CreateResult

log = logging.getLogger("dockyard")

# Transportfel från docker-SDK:t (requests) som inte ärver APIError.
_TRANSPORT_ERRORS = (requests.exceptions.RequestException, OSError)


def _under(path: str, prefixes: list[str]) -> bool:
    """True om path är exakt eller ligger under någon prefix (på /-gräns)."""
    for p in prefixes:
        p = p.rstrip("/")
        if not p:
            continue
        if path == p or path.startswith(p + "/"):
            return True
    return False


def _registry_allowed(image: str) -> bool:
    if not config.ALLOWED_REGISTRIES:
        return True
    return any(
        image == r or image.startswith(r.rstrip("/") + "/")
        for r in config.ALLOWED_REGISTRIES
    )


def _split_ref(ref: str) -> tuple[str, str]:
    """Dela 'host:port/repo:tag' i (repo, tag). Digest hanteras separat."""
    if "@" in ref:
        repo, _, digest = ref.partition("@")
        return repo, digest
    last_slash = ref.rfind("/")
    last_colon = ref.rfind(":")
    if last_colon > last_slash:
        return ref[:last_colon], ref[last_colon + 1:]
    return ref, "latest"


def _check_guardrails(spec: ContainerSpec, client: docker.DockerClient) -> None:
    if spec.name in config.PROTECTED_NAMES:
        raise ForbiddenSpec(f"Namnet '{spec.name}' är skyddat och får inte skapas.")

    if config.ALLOWED_NAME_PREFIXES and not any(
        spec.name.startswith(p) for p in config.ALLOWED_NAME_PREFIXES
    ):
        raise ForbiddenSpec(
            "Containernamnet måste börja med ett tillåtet prefix: "
            + ", ".join(config.ALLOWED_NAME_PREFIXES)
        )

    if not _registry_allowed(spec.image):
        raise ForbiddenSpec(
            "Image:n måste komma från ett tillåtet registry/repo: "
            + ", ".join(config.ALLOWED_REGISTRIES)
        )

    if spec.privileged and not config.ALLOW_PRIVILEGED:
        raise ForbiddenSpec(
            "Privilegierade containrar är avstängda (ger i praktiken root på "
            "hosten). Sätt ALLOW_PRIVILEGED=true för att tillåta."
        )

    for v in spec.volumes:
        host = v.host.rstrip("/") or "/"
        if host == "/" or _under(host, config.DENIED_VOLUME_PREFIXES):
            raise ForbiddenSpec(f"Volym-host '{v.host}' är i en nekad systemkatalog.")
        if not _under(host, config.ALLOWED_VOLUME_PREFIXES):
            raise ForbiddenSpec(
                f"Volym-host '{v.host}' är utanför tillåtna prefix: "
                + ", ".join(config.ALLOWED_VOLUME_PREFIXES)
            )

    for d in spec.devices:
        dev = d.split(":", 1)[0]
        if not config.ALLOWED_DEVICE_PREFIXES or not _under(
            dev, config.ALLOWED_DEVICE_PREFIXES
        ):
            raise ForbiddenSpec(
                f"Device '{d}' är inte tillåten (sätt ALLOWED_DEVICE_PREFIXES)."
            )

    # Exakt namnkrock (filter är substring, så verifiera exakt).
    try:
        existing = client.containers.list(all=True, filters={"name": spec.name})
    except APIError as e:
        raise DockerBackendError(f"Kunde inte kontrollera befintliga containrar: {e}")
    for c in existing:
        if c.name == spec.name:
            raise ConflictError(f"En container med namnet '{spec.name}' finns redan.")


def _labels(spec: ContainerSpec) -> dict[str, str]:
    labels = dict(spec.labels)
    labels[config.MANAGED_LABEL] = "true"
    labels["net.unraid.docker.managed"] = "dockerman"
    if spec.webui:
        labels["net.unraid.docker.webui"] = spec.webui
    if spec.icon:
        labels["net.unraid.docker.icon"] = spec.icon
    return labels


def _ports(spec: ContainerSpec) -> dict[str, int]:
    return {f"{p.container}/{p.proto}": p.host for p in spec.ports}


def _volumes(spec: ContainerSpec) -> dict[str, dict]:
    return {v.host: {"bind": v.container, "mode": v.mode} for v in spec.volumes}


def create_container(spec: ContainerSpec, client: docker.DockerClient) -> CreateResult:
    _check_guardrails(spec, client)
    warnings: list[str] = []

    repo, tag = _split_ref(spec.image)
    log.info("Pullar image %s:%s", repo, tag)
    try:
        client.images.pull(repo, tag=tag)
    except (ImageNotFound, NotFound):
        raise DockerBackendError(f"Image hittades inte: {spec.image}")
    except (APIError, *_TRANSPORT_ERRORS) as e:
        raise DockerBackendError(f"Kunde inte pulla image {spec.image}: {e}")

    restart = spec.restart or config.DEFAULT_RESTART
    log.info("Skapar container %s (%s)", spec.name, spec.image)
    try:
        container = client.containers.create(
            image=spec.image,
            name=spec.name,
            detach=True,
            network=spec.network,
            ports=_ports(spec),
            volumes=_volumes(spec),
            environment=spec.env,
            labels=_labels(spec),
            devices=spec.devices,
            privileged=spec.privileged,
            restart_policy={"Name": restart},
        )
    except APIError as e:
        # Race: någon hann skapa samma namn mellan kontroll och create.
        if e.response is not None and e.response.status_code == 409:
            raise ConflictError(f"En container med namnet '{spec.name}' finns redan.")
        raise DockerBackendError(f"Kunde inte skapa container: {e}")
    except _TRANSPORT_ERRORS as e:
        raise DockerBackendError(f"Kunde inte skapa container: {e}")

    if spec.autostart:
        try:
            container.start()
        except (APIError, *_TRANSPORT_ERRORS) as e:
            warnings.append(f"Container skapad men kunde inte startas: {e}")

    try:
        container.reload()
        state = container.status
    except APIError:
        state = "unknown"

    template_written: str | None = None
    if config.WRITE_TEMPLATE:
        try:
            template_written = template.write(spec)
        except OSError as e:
            warnings.append(f"Container skapad men template-XML kunde inte skrivas: {e}")

    return CreateResult(
        ok=True,
        name=spec.name,
        container_id=container.id,
        image=spec.image,
        state=state,
        template_written=template_written,
        warnings=warnings,
    )


def ping(client: docker.DockerClient) -> bool:
    try:
        return bool(client.ping())
    except Exception:
        return False
