from __future__ import annotations

import time
import uuid
from threading import Lock
from typing import Any

from pydantic import BaseModel, Field

from app.agent.state import AgentRunResponse


class CallSession(BaseModel):
    session_id: str
    created_epoch: float = Field(default_factory=lambda: time.time())
    to_e164: str
    reconcile_payload: dict[str, Any] = Field(default_factory=dict)
    agent_snapshot: dict[str, Any] = Field(default_factory=dict)
    status: str = "dialing"  # dialing | ringing | completed | failed
    twilio_call_sid: str | None = None
    speech_snippets: list[str] = Field(default_factory=list)
    merged_final: dict[str, Any] | None = None
    merge_branch: str | None = None
    error: str | None = None


_lock = Lock()
_sessions: dict[str, CallSession] = {}


def jsonable_agent(agent: AgentRunResponse) -> dict[str, Any]:
    return agent.model_dump(mode="json")


def create_session(*, to_e164: str, agent: AgentRunResponse, reconcile_payload: dict[str, Any]) -> CallSession:
    session_id = uuid.uuid4().hex
    sess = CallSession(
        session_id=session_id,
        to_e164=to_e164,
        reconcile_payload=reconcile_payload,
        agent_snapshot=jsonable_agent(agent),
    )
    with _lock:
        _sessions[session_id] = sess
    return sess


def get_session(session_id: str) -> CallSession | None:
    with _lock:
        return _sessions.get(session_id)


def update_session(session_id: str, **kwargs: Any) -> None:
    with _lock:
        s = _sessions.get(session_id)
        if not s:
            return
        data = s.model_dump()
        data.update(kwargs)
        _sessions[session_id] = CallSession.model_validate(data)


def append_speech(session_id: str, text: str) -> None:
    with _lock:
        s = _sessions.get(session_id)
        if not s:
            return
        parts = list(s.speech_snippets)
        parts.append(text)
        _sessions[session_id] = s.model_copy(update={"speech_snippets": parts})
