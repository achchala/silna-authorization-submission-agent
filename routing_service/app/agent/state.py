from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models import CaseMetadata, RoutingAnalyzeResponse


class StepRecord(BaseModel):
    name: str
    detail: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentRunRequest(BaseModel):
    """Full-agent run: same inputs as single-shot analyze, plus optional Voiceflow callback transcript."""

    instruction_text: str = Field(..., min_length=1)
    case: CaseMetadata = Field(default_factory=CaseMetadata)
    phone_transcript: str | None = Field(
        default=None,
        description="Paste transcript from outbound confirmation call (e.g. from Voiceflow).",
    )


class AgentRunResponse(BaseModel):
    final: RoutingAnalyzeResponse
    steps: list[StepRecord] = Field(default_factory=list)
    branch_taken: Literal["merge", "phone_confirm", "human_research", "merge_after_call", "research_after_call"]
