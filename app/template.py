"""Rendera Unraid-template-XML från en ContainerSpec.

En matchande my-<Name>.xml i templates-user gör att Unraids Docker-flik
associerar den körande containern med en template (ikon, WebUI, update, edit).
"""
import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import config
from .schemas import ContainerSpec

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["xml", "j2"], default=True),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _registry(image: str) -> str:
    """Härled registry-URL för template-fältet (best effort)."""
    ref = image.split("@")[0]  # släng ev. digest
    last_slash = ref.rfind("/")
    last_colon = ref.rfind(":")
    if last_colon > last_slash:  # släng tag så den inte tas för registry-port
        ref = ref[:last_colon]
    first = ref.split("/")[0]
    if "." in first or ":" in first:  # har värd => explicit registry
        return f"https://{first}/"
    return "https://hub.docker.com/"


def _configs(spec: ContainerSpec) -> list[dict]:
    out: list[dict] = []
    for p in spec.ports:
        out.append({
            "name": f"Port {p.container}/{p.proto}", "target": str(p.container),
            "default": str(p.host), "mode": p.proto, "type": "Port",
            "required": "true", "description": "", "value": str(p.host),
        })
    for v in spec.volumes:
        out.append({
            "name": f"Path {v.container}", "target": v.container,
            "default": v.host, "mode": v.mode, "type": "Path",
            "required": "true", "description": "", "value": v.host,
        })
    for k, val in spec.env.items():
        out.append({
            "name": k, "target": k, "default": "", "mode": "",
            "type": "Variable", "required": "false", "description": "", "value": val,
        })
    for d in spec.devices:
        out.append({
            "name": f"Device {d}", "target": d, "default": d, "mode": "",
            "type": "Device", "required": "false", "description": "", "value": d,
        })
    return out


def render(spec: ContainerSpec) -> str:
    tmpl = _env.get_template("unraid_container.xml.j2")
    return tmpl.render(
        name=spec.name,
        image=spec.image,
        registry=_registry(spec.image),
        network=spec.network,
        privileged=spec.privileged,
        support=spec.support or "",
        project=spec.project or "",
        overview=spec.overview or "",
        category=spec.category or "",
        webui=spec.webui or "",
        icon=spec.icon or "",
        date_installed=int(time.time()),
        managed_label=config.MANAGED_LABEL,
        configs=_configs(spec),
    )


def write(spec: ContainerSpec) -> str:
    """Skriv template-XML till TEMPLATE_DIR, returnera sökvägen."""
    path = config.template_path(spec.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(spec), encoding="utf-8")
    return str(path)
