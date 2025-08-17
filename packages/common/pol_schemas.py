from pydantic import BaseModel, Field


class Envelope(BaseModel):
    scenario_id: str
    source: str  # "ais" | "adsb" | "ground"
    ts: str
    entity_id: str
    lat: float
    lon: float
    speed: float | None = None
    course: float | None = None
    alt: float | None = None
    attrs: dict = Field(default_factory=dict)
    h3: str | None = None


class DomainAnomaly(BaseModel):
    ts: str
    domain: str  # "maritime" | "air" | "ground"
    entity_id: str
    h3: str
    type: str  # "loiter" | "rendezvous" | "holding" | "convoy" | "dark_gap" | ...
    score: float
    evidence: dict


class FusedAnomaly(BaseModel):
    ts: str
    cluster_id: str
    types: list[str]
    h3_center: str
    entities: list[str]
    confidence: float
    evidence_links: list[str] = Field(default_factory=list)
