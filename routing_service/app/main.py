import json

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agent.pipeline import run_agent
from app.agent.state import AgentRunRequest, AgentRunResponse
from app.config import Settings, get_settings
from app.gemini_client import analyze_routing
from app.models import RoutingAnalyzeRequest, RoutingAnalyzeResponse


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
