"""Separate CV facts, unverified model opinions and the conservative review decision."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from ep_engine.v31.contracts import Contract, InspectionReport
from ep_engine.vlm_eval.contracts import Mode, Reply
from ep_engine.vlm_eval.evidence import cv_prediction, verified_pairs


class VLMObservation(Contract):
    status: Literal["completed", "failed", "not_run", "offline_fixture"]
    reason: str
    interpretation: Reply | None = None
    supported_prediction: bool | None = None
    findings_verified: Literal[False] = False
    reasoning_scope: Literal[
        "cv_supported_regions",
        "unverified_visual_only",
        "unverified_visual_only_cv_geometry_inconclusive",
    ] = "unverified_visual_only"
    elapsed_seconds: float = Field(ge=0)
    cache_hit: bool = False
    usage: dict[str, int | None] = Field(default_factory=dict)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    provider_reported_cost_usd: float | None = Field(default=None, ge=0)


class CombinedReport(Contract):
    schema_version: Literal["ep-v31-optional-vlm-1.0"] = "ep-v31-optional-vlm-1.0"
    inspection_id: UUID
    mode: Mode
    cv_report: InspectionReport | None
    vlm: VLMObservation | None
    cv_appearance_prediction: bool | None
    vlm_appearance_opinion: bool | None
    supported_appearance_prediction: bool | None
    decision: Literal["cv_only", "cv_fallback", "uncertain", "appearance_hypothesis"]
    disagreement: bool
    uncertainty: list[str]
    recapture_guidance: list[str]
    physical_identity_verified: Literal[False] = False
    confirmed_damage: Literal[False] = False
    payment_action: Literal["none"] = "none"
    human_review_required: Literal[True] = True


def fuse(inspection_id, mode, report, row=None):
    cv = cv_prediction(report) if report is not None else None
    geometry_unverified = (
        mode == "hybrid" and report is not None and not verified_pairs(report.cv_package)
    )
    reply = Reply.model_validate(row["reply"]) if row and row.get("reply") else None
    opinion = (
        None
        if reply is None or reply.change == "uncertain"
        else (reply.change == "visible_difference")
    )
    disagreement = cv is not None and opinion is not None and cv != opinion
    vlm = (
        VLMObservation(
            status=row["status"],
            reason=row["reason"],
            interpretation=reply,
            supported_prediction=None if geometry_unverified else row.get("prediction"),
            reasoning_scope=row.get("reasoning_scope", "unverified_visual_only"),
            elapsed_seconds=row.get("elapsed_seconds", 0),
            cache_hit=row.get("cache_hit", False),
            usage=row.get("usage", {}),
            estimated_cost_usd=row.get("estimated_cost_usd"),
            provider_reported_cost_usd=row.get("provider_reported_cost_usd"),
        )
        if row
        else None
    )
    if mode == "cv_only":
        prediction, decision = cv, "cv_only"
    elif row is None or row["status"] not in {"completed", "offline_fixture"}:
        prediction, decision = (
            cv if mode == "hybrid" else None,
            "cv_fallback" if report else "uncertain",
        )
    elif (
        geometry_unverified
        or disagreement
        or row.get("prediction") is None
        or row["status"] == "offline_fixture"
    ):
        prediction, decision = None, "uncertain"
    else:
        prediction, decision = row["prediction"], "appearance_hypothesis"
    return CombinedReport(
        inspection_id=inspection_id,
        mode=mode,
        cv_report=report,
        vlm=vlm,
        cv_appearance_prediction=cv,
        vlm_appearance_opinion=opinion,
        supported_appearance_prediction=prediction,
        decision=decision,
        disagreement=disagreement,
        uncertainty=[
            "Physical identity and physical damage causation are unverified.",
            "Only visible assessed surfaces are covered; scores are not calibrated probabilities.",
            *(["CV and VLM disagree; preserve both for human review."] if disagreement else []),
            *(reply.uncertainty if reply else []),
        ],
        recapture_guidance=(
            reply.recapture_guidance
            if reply and reply.recapture_guidance
            else [
                "Capture the same object surface from matching angles in diffuse light.",
                "Add a sharp close-up and a wider context image of each questioned region.",
            ]
        ),
    )
