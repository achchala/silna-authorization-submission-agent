from typing import Literal

from pydantic import BaseModel, Field


class CaseMetadata(BaseModel):
    """Structured hints for routing. All fields optional for prototyping."""

    payer_name_guess: str | None = None
    plan_name: str | None = None
    member_id_last4: str | None = None
    cpt_or_hcpcs: str | None = None
    setting: Literal["inpatient", "outpatient", "unknown"] = "unknown"
    urgency: Literal["standard", "urgent", "unknown"] = "unknown"
    facility_or_provider: str | None = None


class RoutingAnalyzeRequest(BaseModel):
    """Paste synthetic payer / auth instruction text plus optional case hints."""

    instruction_text: str = Field(..., min_length=1, description="OCR or pasted routing instructions.")
    case: CaseMetadata = Field(default_factory=CaseMetadata)


class EvidenceItem(BaseModel):
    quote: str
    source: str = Field(description="e.g. page_3_footer, table_row_2")


class RoutingHypothesis(BaseModel):
    channel: Literal["portal", "fax", "email", "mail", "unknown", "multiple"]
    destination: str | None = Field(
        default=None,
        description="Normalized destination: URL, E.164 fax, email, or structured mailing lines.",
    )
    confidence_0_to_1: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    notes: str | None = None


class PhoneConfirmationPlan(BaseModel):
    required: bool = False
    reason: str | None = None
    questions_for_representative: list[str] = Field(default_factory=list)
    read_back_script: str | None = None


class RoutingAnalyzeResponse(BaseModel):
    payer_resolution: str
    payer_candidates: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    hypotheses: list[RoutingHypothesis] = Field(default_factory=list)
    recommended: RoutingHypothesis | None = None
    next_action: Literal["merge", "phone_confirm", "human_research"]
    phone: PhoneConfirmationPlan = Field(default_factory=PhoneConfirmationPlan)
    raw_model_notes: str | None = Field(
        default=None,
        description="Optional short rationale; keep non-PHI for logs.",
    )
