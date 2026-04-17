from pydantic import BaseModel, ConfigDict, Field

from app.models import RoutingHypothesis


class ReconcileResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    payer_resolution: str
    payer_candidates: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    hypotheses: list[RoutingHypothesis] = Field(default_factory=list)
    recommended: RoutingHypothesis | None = None
    raw_model_notes: str | None = None
