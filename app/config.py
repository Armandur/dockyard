"""Konfiguration lastad från miljön (.env i lokal dev)."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _csv(name: str) -> list[str]:
    raw = os.environ.get(name, "").strip()
    return [p.strip() for p in raw.split(",") if p.strip()]


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


# Auth: krävs. Utan nyckel vägrar appen starta (fail-closed).
API_KEY = os.environ.get("API_KEY", "").strip()

# Docker-motorn nås via socket-proxyn, aldrig socketen direkt.
DOCKER_HOST = os.environ.get("DOCKER_HOST", "tcp://socket-proxy:2375").strip()
DOCKER_TIMEOUT = int(os.environ.get("DOCKER_TIMEOUT", "120"))

# Unraids template-katalog, monterad rw. Tom => skriv ingen template.
TEMPLATE_DIR = os.environ.get("TEMPLATE_DIR", "/templates-user").strip()
WRITE_TEMPLATE = _bool("WRITE_TEMPLATE", True)

# Guardrails.
# Tillåtna namn-prefix (tom lista = tillåt alla namn som inte krockar).
ALLOWED_NAME_PREFIXES = _csv("ALLOWED_NAME_PREFIXES")
# Tillåtna image-registries/repos (tom lista = tillåt alla). Matchas som prefix.
ALLOWED_REGISTRIES = _csv("ALLOWED_REGISTRIES")
# Skapa aldrig containrar med dessa exakta namn (skydd för prod).
PROTECTED_NAMES = set(_csv("PROTECTED_NAMES"))

# Enkel rate limit på create (anrop per fönster).
RATELIMIT_MAX = int(os.environ.get("RATELIMIT_MAX", "10"))
RATELIMIT_WINDOW_S = int(os.environ.get("RATELIMIT_WINDOW_S", "60"))

# Standard restart-policy om spec inte anger.
DEFAULT_RESTART = os.environ.get("DEFAULT_RESTART", "unless-stopped").strip()

# Label som stämplas på allt shimmen skapar (för spårbarhet + framtida städning).
MANAGED_LABEL = "dockyard.managed"


def validate() -> None:
    if not API_KEY:
        raise RuntimeError("API_KEY saknas - sätt den i miljön/.env innan start.")
    if len(API_KEY) < 16:
        raise RuntimeError("API_KEY är för kort (minst 16 tecken).")
    if WRITE_TEMPLATE and not TEMPLATE_DIR:
        raise RuntimeError("WRITE_TEMPLATE är på men TEMPLATE_DIR är tom.")


def template_path(name: str) -> Path:
    return Path(TEMPLATE_DIR) / f"my-{name}.xml"
