from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

StatKey = Literal["FRT", "RFX", "ACU", "RSV", "PRS"]
ProficiencyState = Literal["raise", "lower", "lock"]


class ProficiencyLeafDefinition(BaseModel):
    """Authoritative definition for one leaf proficiency (from content)."""

    id: str = Field(..., min_length=3, description="Dot path, e.g. combat.melee.blades")
    name: str = Field(default="", description="Display name; defaults derived in loader if empty")
    description: str = ""
    domain: str = Field(..., min_length=1, description="Top-level domain id, e.g. combat")
    stat_weights: dict[str, float] = Field(default_factory=dict)
    tree_depth: int = Field(
        default=0,
        ge=0,
        le=4,
        description="0=auto from id segment count (clamped 1-4); else explicit tier for gating",
    )
    tags: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _id_normalized(cls, v: str) -> str:
        s = (v or "").strip()
        if ".." in s or s.startswith(".") or s.endswith("."):
            raise ValueError("invalid proficiency id")
        return s

    @field_validator("stat_weights")
    @classmethod
    def _weights(cls, v: dict[str, float]) -> dict[str, float]:
        allowed = {"FRT", "RFX", "ACU", "RSV", "PRS"}
        out: dict[str, float] = {}
        for k, x in (v or {}).items():
            ku = str(k).upper()
            if ku not in allowed:
                raise ValueError(f"unknown stat weight key: {k}")
            out[ku] = float(x)
        s = sum(out.values())
        if s > 0 and abs(s - 1.0) > 0.02:
            raise ValueError(f"stat_weights must sum to ~1.0, got {s}")
        return out


class ProficiencyCatalogDocument(BaseModel):
    """Root document for content/proficiencies/catalog.json (or merged shards)."""

    version: int = 1
    expected_leaf_count: int | None = None
    leaves: list[ProficiencyLeafDefinition] = Field(default_factory=list)


class ProficiencyNode(BaseModel):
    """Resolved node in the tree (leaf or inferred internal prefix)."""

    id: str
    is_leaf: bool
    domain: str
    name: str
    description: str = ""
    tree_depth: int = Field(ge=1, le=4)
    stat_weights: dict[str, float] = Field(default_factory=dict)
    children: list[str] = Field(default_factory=list)
    parent_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class ConduitAttributes(BaseModel):
    """
    Five core Conduit stats (stored on character).

    Storage-contract twin: ``fablestar.state.state_types.ConduitAttributes``
    (TypedDict) describes the same fields as raw Redis/Postgres JSON. This
    BaseModel is the validated-construction side; keep field lists in sync.

    Design target (Fablestar Expanse): 65 points at chargen, each 8-23, default 13/13/13/13/13.
    Stored values may differ for legacy rows; see fablestar.proficiencies.bonus.validate_chargen_conduit_allocation
    for strict chargen validation when the UI/API enforces that flow.
    """

    FRT: int = Field(default=10, ge=1, le=200)
    RFX: int = Field(default=10, ge=1, le=200)
    ACU: int = Field(default=10, ge=1, le=200)
    RSV: int = Field(default=10, ge=1, le=200)
    PRS: int = Field(default=10, ge=1, le=200)


class LeafRuntimeState(BaseModel):
    """Per-leaf (or internal node) runtime state on a character."""

    level: int = Field(default=0, ge=0, le=200)
    state: ProficiencyState = "raise"
    peak: int = Field(default=0, ge=0, le=200)


class ProficiencyStatsBlock(BaseModel):
    """Versioned block inside Character.stats JSON."""

    version: int = 1
    conduit_attributes: ConduitAttributes = Field(default_factory=ConduitAttributes)
    proficiencies: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Map proficiency id -> {level, state, peak}",
    )
    archive_domain_spent: dict[str, int] = Field(
        default_factory=dict,
        description="Optional tallies for archive study domain caps (period reset server-side later)",
    )
    combat_hybrid_legacy: bool = Field(
        default=True,
        description="When True, combat may still read legacy strength/dexterity if present",
    )
