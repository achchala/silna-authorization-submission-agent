# Routing service

FastAPI service for **synthetic** prior-auth routing experiments.

- **`POST /v1/routing/analyze`** — one Gemini call (quick baseline).
- **`POST /v1/agent/run`** — **full multi-step agent**: intake → document-quality heuristic → **Gemini extract** → **deterministic rules** (`data/sample_rules.json`) → **Gemini reconcile** → **deterministic gate** → optional **Gemini call interpreter** when `phone_transcript` is supplied (e.g. pasted from Voiceflow) → **synthesize** final `RoutingAnalyzeResponse`.

Each LLM step uses JSON mode + Pydantic validation. The `steps` array in the agent response is an audit trail for demos.

## Setup

```bash
cd routing_service
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Put your key from https://aistudio.google.com/app/apikey into GEMINI_API_KEY=
```

## Run

```bash
cd routing_service
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- **Simple UI:** `http://127.0.0.1:8000/` (static form → same APIs)
- OpenAPI UI: `http://127.0.0.1:8000/docs`
- Health: `GET /health`
- Analyze: `POST /v1/routing/analyze` or `POST /v1/routing/analyze/raw`
- Full agent: `POST /v1/agent/run` or `POST /v1/agent/run/raw`
- **Outbound Twilio call:** `POST /v1/agent/run-and-dial` — if the gate requires phone confirmation, starts a voice call; Twilio posts speech to `/webhooks/twilio/gather`, then Gemini interprets it. Poll `GET /v1/sessions/{session_id}` until `status` is `completed` or `failed`.

### Twilio + ngrok (for real outbound calls)

1. Twilio account + a **Twilio phone number** (`TWILIO_FROM_NUMBER` in E.164).
2. **Trial:** Twilio only lets you call **verified** destination numbers unless you upgrade.
3. Expose this API on **https** (e.g. `ngrok http 8000`) and set **`PUBLIC_BASE_URL`** in `.env` to that https origin (no trailing slash). Twilio must reach `/webhooks/twilio/voice` and `/webhooks/twilio/gather` on the public host, not `localhost`.
4. Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `PUBLIC_BASE_URL`, then use **Agent + Twilio dial** in the UI or `POST /v1/agent/run-and-dial` with `outbound_dial: { "to_e164": "+1..." }`.

Calls are **not free** (Twilio per-minute). This path is optional; `/v1/agent/run` with a pasted transcript still works without Twilio.

## Example curl

```bash
curl -s -X POST http://127.0.0.1:8000/v1/routing/analyze \
  -H 'Content-Type: application/json' \
  -d @example_request.json | jq .

curl -s -X POST http://127.0.0.1:8000/v1/agent/run \
  -H 'Content-Type: application/json' \
  -d @example_agent_run.json | jq .

curl -s -X POST http://127.0.0.1:8000/v1/agent/run \
  -H 'Content-Type: application/json' \
  -d @example_agent_run_with_transcript.json | jq .
```

## Voiceflow

1. Expose this API to the internet with a tunnel (e.g. ngrok) or host it on a small free tier you control.
2. In Voiceflow, add an **API** step: `POST` to `/v1/routing/analyze/raw`, body JSON = your variables, map response fields into session variables for the confirmation flow.
3. Do **not** embed `GEMINI_API_KEY` in Voiceflow; keep the key only on this server.

## Scope

- No real PHI: use fabricated instructions only.
- No OCR in this slice: paste text that already looks like OCR output if you want to simulate noise.
