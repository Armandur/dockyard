"""Pydantic-scheman för create-API:t."""
import re

from pydantic import BaseModel, Field, field_validator

# Docker-container-namn: [a-zA-Z0-9][a-zA-Z0-9_.-]+
_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,62}$")


class PortMapping(BaseModel):
    container: int = Field(ge=1, le=65535)
    host: int = Field(ge=1, le=65535)
    proto: str = "tcp"

    @field_validator("proto")
    @classmethod
    def _proto(cls, v: str) -> str:
        v = v.lower()
        if v not in ("tcp", "udp"):
            raise ValueError("proto måste vara tcp eller udp")
        return v


class VolumeMapping(BaseModel):
    host: str = Field(min_length=1)
    container: str = Field(min_length=1)
    mode: str = "rw"

    @field_validator("mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        v = v.lower()
        if v not in ("rw", "ro"):
            raise ValueError("mode måste vara rw eller ro")
        return v

    @field_validator("container")
    @classmethod
    def _abs(cls, v: str) -> str:
        if not v.startswith("/"):
            raise ValueError("container-sökväg måste vara absolut")
        return v


class ContainerSpec(BaseModel):
    name: str
    image: str = Field(min_length=1)
    network: str = "bridge"
    restart: str | None = None
    privileged: bool = False
    autostart: bool = True  # starta containern efter create

    ports: list[PortMapping] = []
    volumes: list[VolumeMapping] = []
    env: dict[str, str] = {}
    labels: dict[str, str] = {}
    devices: list[str] = []

    # Template-metadata (för Unraids GUI).
    webui: str | None = None       # t.ex. "http://[IP]:[PORT:8080]/"
    icon: str | None = None
    overview: str | None = None
    support: str | None = None
    project: str | None = None
    category: str | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError(
                "ogiltigt containernamn (tillåtet: bokstäver/siffror/._- , 2-63 tecken)"
            )
        return v

    @field_validator("restart")
    @classmethod
    def _restart(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in ("no", "always", "unless-stopped", "on-failure"):
            raise ValueError("restart måste vara no/always/unless-stopped/on-failure")
        return v


class ContainerPatch(BaseModel):
    """Partiell ändring av en befintlig container. None = rör inte fältet.

    env slås ihop med befintliga variabler (så man kan lägga till utan att
    känna till resten); använd env_remove för att ta bort. Listfälten ports,
    volumes, devices och labels ERSÄTTER sina motsvarigheter i sin helhet,
    eftersom en sammanslagning av listor inte har någon entydig innebörd.
    """
    image: str | None = None
    network: str | None = None
    restart: str | None = None
    privileged: bool | None = None

    env: dict[str, str] | None = None
    env_remove: list[str] = []
    ports: list[PortMapping] | None = None
    volumes: list[VolumeMapping] | None = None
    labels: dict[str, str] | None = None
    devices: list[str] | None = None

    webui: str | None = None
    icon: str | None = None
    overview: str | None = None
    support: str | None = None
    project: str | None = None
    category: str | None = None

    # Starta containern efter ombyggnaden. None = behåll det den var.
    autostart: bool | None = None

    @field_validator("restart")
    @classmethod
    def _restart(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in ("no", "always", "unless-stopped", "on-failure"):
            raise ValueError("restart måste vara no/always/unless-stopped/on-failure")
        return v

    def changed_fields(self) -> list[str]:
        """Vilka fält anroparen faktiskt satte - för svaret och loggen."""
        fields = [
            name for name, value in self.model_dump(exclude_defaults=True).items()
            if value is not None
        ]
        return sorted(fields)


class PatchResult(BaseModel):
    ok: bool
    name: str
    container_id: str
    image: str
    state: str
    changed: list[str] = []
    recreated: bool = True
    template_written: str | None = None
    warnings: list[str] = []


class CreateResult(BaseModel):
    ok: bool
    name: str
    container_id: str
    image: str
    state: str
    template_written: str | None = None
    warnings: list[str] = []


class ContainerSummary(BaseModel):
    """En rad i GET /containers - de containrar dockyard hanterar."""
    name: str
    image: str
    state: str
