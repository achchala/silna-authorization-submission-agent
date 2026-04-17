from pydantic import BaseModel, Field

from app.agent.state import AgentRunRequest, AgentRunResponse


class OutboundDialConfig(BaseModel):
    """Destination phone for an outbound confirmation call (E.164)."""

    to_e164: str = Field(..., min_length=8, description='Example: "+15551234567"')


class AgentRunWithDialRequest(AgentRunRequest):
    """Same as agent run plus Twilio outbound dial. Do not send phone_transcript here."""

    outbound_dial: OutboundDialConfig


class OutboundDialResult(BaseModel):
    session_id: str
    call_sid: str
    status: str = "initiated"
    poll_url: str


class AgentRunDialResponse(BaseModel):
    agent: AgentRunResponse
    dial: OutboundDialResult | None = None
    dial_skipped_reason: str | None = None


class SessionPollResponse(BaseModel):
    session_id: str
    status: str
    speech_snippets: list[str] = Field(default_factory=list)
    merged_final: dict | None = None
    merge_branch: str | None = None
    error: str | None = None
