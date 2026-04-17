import json

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.gemini_client import analyze_routing
from app.models import RoutingAnalyzeRequest, RoutingAnalyzeResponse


app = FastAPI(
    title="Prior auth routing analyzer",
    description="MVP: Gemini extracts structured routing recommendations from synthetic instruction text.",
    version="0.1.0",
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


@app.post("/v1/routing/analyze/raw")
def routing_analyze_raw(
    body: RoutingAnalyzeRequest,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Same as /analyze but returns the raw JSON object for Voiceflow APIs that map paths manually."""
    result = _analyze(body, settings)
    return JSONResponse(content=json.loads(result.model_dump_json()))
