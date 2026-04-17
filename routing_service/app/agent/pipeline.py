from __future__ import annotations

import json
from typing import Literal

from app.agent.call_models import CallInterpretation
from app.agent.extraction_models import ExtractionResult
from app.agent.prompts_agent import CALL_SYSTEM, CALL_USER, EXTRACT_SYSTEM, EXTRACT_USER, RECONCILE_SYSTEM, RECONCILE_USER
from app.agent.reconcile_models import ReconcileResult
from app.agent.rules_engine import apply_rules, heuristic_ocr_score, load_rules, resolve_payer_key
from app.agent.state import AgentRunRequest, AgentRunResponse, StepRecord
from app.llm import gemini_generate_json
from app.models import EvidenceItem, PhoneConfirmationPlan, RoutingAnalyzeResponse, RoutingHypothesis


def _gate_next_action(
    *,
    ocr_score: float,
    rec: RoutingHypothesis | None,
    conflicts: list[str],
) -> Literal["merge", "phone_confirm", "human_research"]:
    if ocr_score < 0.45:
        return "phone_confirm"
    if rec is None:
        return "human_research"
    if rec.confidence_0_to_1 < 0.55:
        return "human_research"
    if conflicts and rec.confidence_0_to_1 < 0.88:
        return "phone_confirm"
    if conflicts:
        return "phone_confirm"
    if rec.confidence_0_to_1 >= 0.88 and ocr_score >= 0.5:
        return "merge"
    return "phone_confirm"


def _phone_plan_from_state(
    *,
    next_action: Literal["merge", "phone_confirm", "human_research"],
    rec: RoutingHypothesis | None,
    conflicts: list[str],
    ocr_score: float,
) -> PhoneConfirmationPlan:
    if next_action != "phone_confirm":
        return PhoneConfirmationPlan(
            required=False,
            reason=None if next_action == "merge" else "human_research_queue",
            questions_for_representative=[],
            read_back_script=None,
        )
    dest = rec.destination if rec else None
    ch = rec.channel if rec else "unknown"
    read_back = None
    if dest:
        read_back = (
            f"We have you submitting prior authorization via {ch}, destination {dest}. "
            "Is that still the correct channel and destination for this plan and service type?"
        )
    qs = [
        "For this member plan and outpatient service, what is the correct submission channel: portal, fax, email, or mail?",
        "What exact destination should we use (portal URL, fax number, or email)?",
    ]
    reason_parts = []
    if conflicts:
        reason_parts.append("written conflicts: " + "; ".join(conflicts[:3]))
    if ocr_score < 0.55:
        reason_parts.append("low document-quality score")
    return PhoneConfirmationPlan(
        required=True,
        reason=" | ".join(reason_parts) if reason_parts else "policy_or_medium_confidence",
        questions_for_representative=qs,
        read_back_script=read_back,
    )


def merge_call_into_final(
    base: ReconcileResult,
    call: CallInterpretation,
) -> tuple[RoutingAnalyzeResponse, Literal["merge_after_call", "research_after_call"]]:
    strong = (
        call.representative_confirmed_readback
        and call.confidence_0_to_1 >= 0.72
        and call.confirmed_destination is not None
    )
    hyp = RoutingHypothesis(
        channel=call.confirmed_channel,
        destination=call.confirmed_destination,
        confidence_0_to_1=call.confidence_0_to_1,
        evidence=[
            EvidenceItem(quote="(see phone transcript)", source="phone_call"),
        ],
        notes=call.summary,
    )
    branch: Literal["merge_after_call", "research_after_call"] = "merge_after_call" if strong else "research_after_call"
    next_action: Literal["merge", "phone_confirm", "human_research"] = "merge" if strong else "human_research"
    return (
        RoutingAnalyzeResponse(
            payer_resolution=base.payer_resolution,
            payer_candidates=base.payer_candidates,
            conflicts=list({*base.conflicts, *call.conflicts_with_prior_written}),
            hypotheses=base.hypotheses + [hyp],
            recommended=hyp if strong else base.recommended,
            next_action=next_action,
            phone=PhoneConfirmationPlan(
                required=False,
                reason="call_completed",
                questions_for_representative=[],
                read_back_script=None,
            ),
            raw_model_notes=call.summary,
        ),
        branch,
    )


def run_agent(*, api_key: str, model: str, body: AgentRunRequest) -> AgentRunResponse:
    steps: list[StepRecord] = []
    text = body.instruction_text
    case = body.case

    steps.append(StepRecord(name="intake", detail="validated envelope", payload={"chars": len(text)}))

    ocr_score = heuristic_ocr_score(text)
    steps.append(StepRecord(name="document_signals", detail="heuristic doc-quality score", payload={"ocr_score": ocr_score}))

    extract_prompt = EXTRACT_SYSTEM + "\n\n" + EXTRACT_USER.format(instruction_text=text)
    primitives = gemini_generate_json(
        api_key=api_key,
        model=model,
        prompt=extract_prompt,
        response_model=ExtractionResult,
    )
    steps.append(StepRecord(name="extract", detail="routing primitives", payload=primitives.model_dump()))

    rules = load_rules()
    payer_key = resolve_payer_key(primitives, rules)
    rule_pack = apply_rules(
        payer_key=payer_key,
        case=case,
        primitives=primitives,
        instruction_text=text,
        rules=rules,
    )
    steps.append(
        StepRecord(
            name="rules_engine",
            detail="deterministic tables and overrides",
            payload=rule_pack,
        )
    )

    reconcile_prompt = (
        RECONCILE_SYSTEM
        + "\n\n"
        + RECONCILE_USER.format(
            case_json=json.dumps(case.model_dump(), indent=2),
            primitives_json=json.dumps(primitives.model_dump(), indent=2),
            rules_json=json.dumps(rule_pack, indent=2),
            code_conflicts_json=json.dumps(rule_pack.get("code_conflicts") or [], indent=2),
            instruction_text=text,
        )
    )
    reconciled = gemini_generate_json(
        api_key=api_key,
        model=model,
        prompt=reconcile_prompt,
        response_model=ReconcileResult,
    )
    steps.append(StepRecord(name="reconcile", detail="hypotheses and conflicts", payload=reconciled.model_dump()))

    next_action = _gate_next_action(
        ocr_score=ocr_score,
        rec=reconciled.recommended,
        conflicts=reconciled.conflicts,
    )
    steps.append(StepRecord(name="gate", detail="policy and confidence routing", payload={"next_action": next_action}))

    if body.phone_transcript and body.phone_transcript.strip():
        call_prompt = (
            CALL_SYSTEM
            + "\n\n"
            + CALL_USER.format(
                prior_json=json.dumps(reconciled.model_dump(), indent=2),
                transcript=body.phone_transcript.strip(),
            )
        )
        call = gemini_generate_json(
            api_key=api_key,
            model=model,
            prompt=call_prompt,
            response_model=CallInterpretation,
        )
        steps.append(StepRecord(name="call_interpreter", detail="structured transcript parse", payload=call.model_dump()))
        final, branch = merge_call_into_final(reconciled, call)
        steps.append(StepRecord(name="synthesize", detail="merged written + call", payload={"branch": branch}))
        return AgentRunResponse(final=final, steps=steps, branch_taken=branch)

    phone = _phone_plan_from_state(next_action=next_action, rec=reconciled.recommended, conflicts=reconciled.conflicts, ocr_score=ocr_score)

    final = RoutingAnalyzeResponse(
        payer_resolution=reconciled.payer_resolution,
        payer_candidates=reconciled.payer_candidates,
        conflicts=reconciled.conflicts,
        hypotheses=reconciled.hypotheses,
        recommended=reconciled.recommended,
        next_action=next_action,
        phone=phone,
        raw_model_notes=reconciled.raw_model_notes,
    )
    branch = next_action  # type: ignore[assignment]
    steps.append(StepRecord(name="synthesize", detail="no transcript; gate output only", payload={}))
    return AgentRunResponse(final=final, steps=steps, branch_taken=branch)
