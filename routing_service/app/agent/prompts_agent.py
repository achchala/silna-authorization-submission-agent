EXTRACT_SYSTEM = """You extract routing primitives from prior-authorization instruction text for internal ops.
Use ONLY the instruction text. Output valid JSON matching the schema described in the user message.
Do not invent destinations. Quotes must be copied from the instruction text."""

EXTRACT_USER = """Return one JSON object with keys:
- payer_strings: string[]
- plan_strings: string[]
- destinations: array of objects with keys channel_hint (portal|fax|email|mail|unknown), value (string),
  evidence_quote (short substring from instruction text), location_hint (string or null)
- deadlines_or_urgency_notes: string[]
- ocr_noise_indicators: string[] (e.g. garbled tokens if present)

Instruction text:
---
{instruction_text}
---
JSON only, no markdown."""

RECONCILE_SYSTEM = """You reconcile prior-authorization routing evidence for internal ops.
Combine document primitives, deterministic rule hints, and explicit string conflicts.
Output JSON only. Do not invent payers or URLs not present in the inputs."""

RECONCILE_USER = """Given the inputs below, return JSON with keys:
- payer_resolution: string
- payer_candidates: string[]
- conflicts: string[] (include doc-vs-doc and doc-vs-rule conflicts)
- hypotheses: array of RoutingHypothesis-like objects:
    channel: portal|fax|email|mail|unknown|multiple
    destination: string or null
    confidence_0_to_1: number 0-1
    evidence: array of {{ "quote": string, "source": string }}
    notes: string or null
- recommended: one hypothesis object or null
- raw_model_notes: string or null

Case metadata:
{case_json}

Document primitives (from extractor):
{primitives_json}

Rule engine suggestions (may be empty):
{rules_json}

Explicit string conflicts detected in code:
{code_conflicts_json}

Instruction text (for additional evidence quotes):
---
{instruction_text}
---
JSON only, no markdown."""

CALL_SYSTEM = """You interpret a synthetic phone transcript about where to submit a prior authorization.
Compare the transcript to prior written hypotheses. Output JSON only. Do not invent numbers not spoken."""

CALL_USER = """Prior written routing hypotheses (JSON):
{prior_json}

Phone transcript (synthetic / redacted):
---
{transcript}
---

Return JSON with keys:
- confirmed_channel: portal|fax|email|mail|unknown|multiple
- confirmed_destination: string or null
- representative_confirmed_readback: boolean
- conflicts_with_prior_written: string[]
- confidence_0_to_1: number 0-1
- summary: string or null

JSON only, no markdown."""
