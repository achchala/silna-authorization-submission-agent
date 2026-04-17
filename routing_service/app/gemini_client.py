import json
import re
from typing import Any

import google.generativeai as genai

from app.models import RoutingAnalyzeRequest, RoutingAnalyzeResponse
from app.prompts import SYSTEM, USER_TEMPLATE


_JSON_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE | re.MULTILINE)


def _strip_fences(text: str) -> str:
    t = text.strip()
    t = _JSON_FENCE.sub("", t).strip()
    return t


def analyze_routing(*, api_key: str, model: str, payload: RoutingAnalyzeRequest) -> RoutingAnalyzeResponse:
    genai.configure(api_key=api_key)
    generation_config: dict[str, Any] = {"response_mime_type": "application/json"}

    user = USER_TEMPLATE.format(
        case_json=json.dumps(payload.case.model_dump(), indent=2),
        instruction_text=payload.instruction_text,
    )
    # Single text block for broad SDK compatibility (system_instruction varies by version).
    prompt = f"{SYSTEM}\n\n{user}"

    gm = genai.GenerativeModel(model_name=model, generation_config=generation_config)
    response = gm.generate_content(prompt)
    text = getattr(response, "text", None) or ""
    if not text.strip():
        # Some failures populate prompt_feedback / candidates without .text
        raise RuntimeError("Gemini returned an empty response; check API key, model name, and quota.")

    cleaned = _strip_fences(text)
    data = json.loads(cleaned)
    return RoutingAnalyzeResponse.model_validate(data)
