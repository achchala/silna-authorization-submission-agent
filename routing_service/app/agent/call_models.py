from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CallInterpretation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    confirmed_channel: Literal["portal", "fax", "email", "mail", "unknown", "multiple"]
    confirmed_destination: str | None = None
    representative_confirmed_readback: bool = False
    conflicts_with_prior_written: list[str] = Field(default_factory=list)
    confidence_0_to_1: float = Field(ge=0.0, le=1.0)
    summary: str | None = None
