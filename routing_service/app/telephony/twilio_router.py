from __future__ import annotations

import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, Response
from twilio.twiml.voice_response import Gather, VoiceResponse

from app.agent.call_models import CallInterpretation
from app.agent.pipeline import merge_call_into_final
from app.agent.prompts_agent import CALL_SYSTEM, CALL_USER
from app.agent.reconcile_models import ReconcileResult
from app.config import Settings, get_settings
from app.llm import gemini_generate_json
from app.telephony.sessions import append_speech, get_session, update_session

router = APIRouter(tags=["twilio"])


def _public_base(settings: Settings) -> str:
    b = (settings.public_base_url or "").strip().rstrip("/")
    if not b.startswith("https://"):
        raise ValueError("PUBLIC_BASE_URL must be https://... so Twilio can reach webhooks (use ngrok).")
    return b


def _say_text(text: str | None, *, max_len: int = 3500) -> str:
    if not text:
        return "No read-back script is available. Please describe the correct submission channel and destination."
    return text.strip()[:max_len]


@router.api_route("/webhooks/twilio/voice", methods=["GET", "POST"])
async def twilio_voice(
    session_id: str = Query(..., min_length=8),
    settings: Settings = Depends(get_settings),
) -> Response:
    sess = get_session(session_id)
    if not sess:
        vr = VoiceResponse()
        vr.say("This confirmation link is invalid or has expired.")
        vr.hangup()
        return Response(content=str(vr), media_type="application/xml")

    try:
        base = _public_base(settings)
    except ValueError as e:
        vr = VoiceResponse()
        vr.say(f"Configuration error: {e}")
        vr.hangup()
        return Response(content=str(vr), media_type="application/xml")
    gather_url = f"{base}/webhooks/twilio/gather?session_id={quote(session_id, safe='')}"

    agent_final = sess.agent_snapshot.get("final") or {}
    read_back = (agent_final.get("phone") or {}).get("read_back_script")
    if not read_back:
        rec = agent_final.get("recommended")
        if isinstance(rec, dict) and rec.get("destination"):
            read_back = (
                f"We believe prior authorization should go via {rec.get('channel')}, "
                f"destination {rec.get('destination')}. Please confirm or correct."
            )
        else:
            read_back = "We need to confirm where to submit this prior authorization."

    vr = VoiceResponse()
    vr.say(_say_text(read_back), voice="Polly.Joanna")
    g = Gather(
        input="speech",
        action=gather_url,
        method="POST",
        speech_timeout="auto",
        language="en-US",
    )
    g.say(
        "If that is correct, say confirmed. Otherwise, say the correct portal, fax number, or email.",
        voice="Polly.Joanna",
    )
    vr.append(g)
    vr.say("We did not hear a response. Goodbye.", voice="Polly.Joanna")
    vr.hangup()

    update_session(session_id, status="ringing")
    return Response(content=str(vr), media_type="application/xml")


@router.post("/webhooks/twilio/gather")
async def twilio_gather(
    request: Request,
    session_id: str = Query(..., min_length=8),
    settings: Settings = Depends(get_settings),
) -> Response:
    sess = get_session(session_id)
    vr = VoiceResponse()
    if not sess:
        vr.say("Session not found.")
        vr.hangup()
        return Response(content=str(vr), media_type="application/xml")

    form = await request.form()
    speech = (form.get("SpeechResult") or form.get("UnstableSpeechResult") or "").strip()
    append_speech(session_id, speech or "(empty)")

    if not speech:
        update_session(session_id, status="failed", error="empty_speech_result")
        vr.say("We could not understand the response. Please try again from the application.")
        vr.hangup()
        return Response(content=str(vr), media_type="application/xml")

    transcript = (
        "Automated call capture (speech-to-text, may contain errors): "
        f"The representative or party said: {speech}"
    )

    try:
        reconciled = ReconcileResult.model_validate(sess.reconcile_payload)
        call_prompt = (
            CALL_SYSTEM
            + "\n\n"
            + CALL_USER.format(
                prior_json=json.dumps(sess.reconcile_payload, indent=2),
                transcript=transcript,
            )
        )
        call = gemini_generate_json(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            prompt=call_prompt,
            response_model=CallInterpretation,
        )
        final, branch = merge_call_into_final(reconciled, call)
        update_session(
            session_id,
            status="completed",
            merged_final=final.model_dump(mode="json"),
            merge_branch=branch,
        )
        vr.say("Thank you. You may hang up now.", voice="Polly.Joanna")
    except Exception as e:  # noqa: BLE001 — demo surface; log in production
        update_session(session_id, status="failed", error=str(e))
        vr.say("Sorry, we could not complete the automated capture. Goodbye.", voice="Polly.Joanna")

    vr.hangup()
    return Response(content=str(vr), media_type="application/xml")


@router.post("/webhooks/twilio/status")
async def twilio_status(
    request: Request,
    session_id: str = Query(..., min_length=8),
) -> dict[str, str]:
    """Optional Twilio status callback."""
    form = await request.form()
    st = (form.get("CallStatus") or "").strip()
    if st in {"ringing", "in-progress"}:
        update_session(session_id, status=st.replace("-", "_"))
    return {"ok": "true"}
