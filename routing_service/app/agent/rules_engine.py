from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.agent.extraction_models import ExtractionResult
from app.models import CaseMetadata


def _default_rules_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "data" / "sample_rules.json"


def load_rules(path: Path | None = None) -> dict[str, Any]:
    p = path or _default_rules_path()
    if not p.exists():
        return {"payer_aliases": {}, "routing_by_payer_key": {}, "overrides": []}
    return json.loads(p.read_text(encoding="utf-8"))


def resolve_payer_key(primitives: ExtractionResult, rules: dict[str, Any]) -> str | None:
    aliases: dict[str, list[str]] = rules.get("payer_aliases") or {}
    blob = " ".join(primitives.payer_strings).upper()
    for key, names in aliases.items():
        for n in names:
            if n.upper() in blob or n.upper() in blob.replace("-", " "):
                return key
    return None


def apply_rules(
    *,
    payer_key: str | None,
    case: CaseMetadata,
    primitives: ExtractionResult,
    instruction_text: str,
    rules: dict[str, Any],
) -> dict[str, Any]:
    """Deterministic suggestions and flags. Returns dict for reconcile + gate."""
    out: dict[str, Any] = {
        "payer_key": payer_key,
        "rule_suggestions": [],
        "code_conflicts": [],
        "override_hits": [],
    }
    routing = rules.get("routing_by_payer_key") or {}
    if payer_key and payer_key in routing:
        by_setting = routing[payer_key]
        setting = case.setting if case.setting != "unknown" else "outpatient"
        row = by_setting.get(setting) or by_setting.get("default")
        if row:
            out["rule_suggestions"].append(
                {
                    "channel": row.get("channel"),
                    "destination": row.get("destination"),
                    "source": row.get("source", "routing_table"),
                    "notes": row.get("notes"),
                }
            )

    for ov in rules.get("overrides") or []:
        needle = (ov.get("match_substring") or "").strip()
        if needle and needle in instruction_text:
            out["override_hits"].append(ov)
            if ov.get("action") == "deprecate_destination":
                out["code_conflicts"].append(
                    f"Override {ov.get('id')}: document contains deprecated destination substring '{needle}'."
                )

    # Doc vs rule: if rule suggests portal but doc lists distinct fax for same payer context
    faxes = [d.value for d in primitives.destinations if d.channel_hint == "fax"]
    for sug in out["rule_suggestions"]:
        if sug.get("channel") == "portal" and faxes:
            out["code_conflicts"].append("Rule prefers portal but document lists fax destination(s); verify.")

    return out


def heuristic_ocr_score(instruction_text: str) -> float:
    """Cheap stand-in for layout/OCR confidence (0 weak, 1 strong)."""
    t = instruction_text
    if len(t) < 40:
        return 0.35
    non_ascii = sum(1 for c in t if ord(c) > 126)
    ratio = non_ascii / max(len(t), 1)
    return max(0.0, min(1.0, 1.0 - min(ratio * 8.0, 0.6)))
