import json
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.agent.pipeline import run_agent
from app.agent.state import AgentRunRequest, AgentRunResponse
from app.config import Settings, get_settings
from app.gemini_client import analyze_routing
from app.models import RoutingAnalyzeRequest, RoutingAnalyzeResponse
from app.telephony.schemas import AgentRunDialResponse, AgentRunWithDialRequest, OutboundDialResult, SessionPollResponse
from app.telephony.sessions import create_session, get_session, update_session
from app.telephony.twilio_dial import start_outbound_call
from app.telephony.twilio_router import router as twilio_router

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(
    title="Prior auth routing analyzer",
    description="Single-shot analyze plus multi-step /v1/agent/run (extract → rules → reconcile → gate → optional call parse).",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(twilio_router)


@app.get("/")
def ui() -> FileResponse:
    index = STATIC_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="UI not found (static/index.html missing).")
    return FileResponse(index, media_type="text/html; charset=utf-8")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _analyze(body: RoutingAnalyzeRequest, settings: Settings) -> RoutingAnalyzeResponse:
    try:
        return analyze_routing(api_key=settings.gemini_api_key, model=settings.gemini_model, payload=body)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail=f"Model did not return valid JSON: {e}") from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.post("/v1/routing/analyze", response_model=RoutingAnalyzeResponse)
def routing_analyze(
    body: RoutingAnalyzeRequest,
    settings: Settings = Depends(get_settings),
) -> RoutingAnalyzeResponse:
    return _analyze(body, settings)


def _run_agent(body: AgentRunRequest, settings: Settings) -> AgentRunResponse:
    try:
        return run_agent(api_key=settings.gemini_api_key, model=settings.gemini_model, body=body)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail=f"Model did not return valid JSON: {e}") from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.post("/v1/agent/run", response_model=AgentRunResponse)
def agent_run(
    body: AgentRunRequest,
    settings: Settings = Depends(get_settings),
) -> AgentRunResponse:
    """Full internal agent: multiple Gemini nodes + deterministic rules and gate. Optional phone_transcript for Voiceflow callback."""
    return _run_agent(body, settings)


def _twilio_configured(settings: Settings) -> bool:
    pub = (settings.public_base_url or "").strip()
    return bool(
        settings.twilio_account_sid
        and settings.twilio_auth_token
        and settings.twilio_from_number
        and pub.lower().startswith("https://"),
    )


@app.post("/v1/agent/run-and-dial", response_model=AgentRunDialResponse)
def agent_run_and_dial(
    body: AgentRunWithDialRequest,
    settings: Settings = Depends(get_settings),
) -> AgentRunDialResponse:
    """Run the full agent; if the gate requires phone confirmation, place an outbound Twilio call to collect speech."""
    if body.phone_transcript:
        raise HTTPException(
            status_code=400,
            detail="Use either outbound_dial (this endpoint) or phone_transcript (/v1/agent/run), not both.",
        )
    if not _twilio_configured(settings):
        raise HTTPException(
            status_code=400,
            detail="Twilio not configured. Set PUBLIC_BASE_URL (https), TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER in .env",
        )

    req = AgentRunRequest(instruction_text=body.instruction_text, case=body.case)
    agent = _run_agent(req, settings)

    if agent.final.next_action != "phone_confirm" or not agent.final.phone.required:
        return AgentRunDialResponse(
            agent=agent,
            dial=None,
            dial_skipped_reason="Gate did not require phone confirmation (merge or human_research). No call placed.",
        )

    reconcile_payload: dict = {}
    for step in agent.steps:
        if step.name == "reconcile":
            reconcile_payload = dict(step.payload)
            break

    to_e164 = body.outbound_dial.to_e164.strip().replace(" ", "")
    if not to_e164.startswith("+"):
        raise HTTPException(status_code=400, detail="outbound_dial.to_e164 must be E.164 and start with +, e.g. +15551234567")

    sess = create_session(to_e164=to_e164, agent=agent, reconcile_payload=reconcile_payload)
    base = settings.public_base_url.strip().rstrip("/")  # type: ignore[union-attr]
    voice_url = f"{base}/webhooks/twilio/voice?session_id={sess.session_id}"
    status_url = f"{base}/webhooks/twilio/status?session_id={sess.session_id}"

    try:
        sid = start_outbound_call(
            account_sid=settings.twilio_account_sid,  # type: ignore[arg-type]
            auth_token=settings.twilio_auth_token,  # type: ignore[arg-type]
            from_number=settings.twilio_from_number,  # type: ignore[arg-type]
            to_e164=to_e164,
            voice_url=voice_url,
            status_callback=status_url,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Twilio call failed: {e}") from e

    update_session(sess.session_id, twilio_call_sid=sid, status="dialing")

    return AgentRunDialResponse(
        agent=agent,
        dial=OutboundDialResult(
            session_id=sess.session_id,
            call_sid=sid,
            status="initiated",
            poll_url=f"/v1/sessions/{sess.session_id}",
        ),
        dial_skipped_reason=None,
    )


@app.get("/v1/sessions/{session_id}", response_model=SessionPollResponse)
def get_call_session(session_id: str) -> SessionPollResponse:
    """Poll after run-and-dial: when status is completed, merged_final has the routing object after call interpretation."""
    sess = get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    return SessionPollResponse(
        session_id=sess.session_id,
        status=sess.status,
        speech_snippets=list(sess.speech_snippets),
        merged_final=sess.merged_final,
        merge_branch=sess.merge_branch,
        error=sess.error,
    )


@app.post("/v1/agent/run/raw")
def agent_run_raw(
    body: AgentRunRequest,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    result = _run_agent(body, settings)
    return JSONResponse(content=json.loads(result.model_dump_json()))


@app.post("/v1/routing/analyze/raw")
def routing_analyze_raw(
    body: RoutingAnalyzeRequest,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Same as /analyze but returns the raw JSON object for Voiceflow APIs that map paths manually."""
    result = _analyze(body, settings)
    return JSONResponse(content=json.loads(result.model_dump_json()))
