import json
import re
from typing import Any, TypeVar

import google.generativeai as genai
from pydantic import BaseModel

_JSON_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE | re.MULTILINE)

T = TypeVar("T", bound=BaseModel)


def strip_json_fences(text: str) -> str:
    t = text.strip()
    t = _JSON_FENCE.sub("", t).strip()
    return t


def gemini_generate_json(
    *,
    api_key: str,
    model: str,
    prompt: str,
    response_model: type[T],
) -> T:
    genai.configure(api_key=api_key)
    generation_config: dict[str, Any] = {"response_mime_type": "application/json"}
    gm = genai.GenerativeModel(model_name=model, generation_config=generation_config)
    response = gm.generate_content(prompt)
    text = getattr(response, "text", None) or ""
    if not text.strip():
        raise RuntimeError("Gemini returned an empty response.")
    data = json.loads(strip_json_fences(text))
    return response_model.model_validate(data)
