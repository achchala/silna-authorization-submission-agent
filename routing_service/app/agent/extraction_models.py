from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DestinationPrimitive(BaseModel):
    model_config = ConfigDict(extra="ignore")

    channel_hint: Literal["portal", "fax", "email", "mail", "unknown"] = "unknown"
    value: str
    evidence_quote: str = Field(..., max_length=500)
    location_hint: str | None = None


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    payer_strings: list[str] = Field(default_factory=list)
    plan_strings: list[str] = Field(default_factory=list)
    destinations: list[DestinationPrimitive] = Field(default_factory=list)
    deadlines_or_urgency_notes: list[str] = Field(default_factory=list)
    ocr_noise_indicators: list[str] = Field(default_factory=list)
