from __future__ import annotations

import json
from pathlib import Path

from .models import (
    EditSuggestion,
    EditSuggestions,
    FeatureContribution,
    PlanScore,
    Recommendation,
    ReelPlan,
    ScoreReport,
)

_DEFAULT_WEIGHTS = {
    "pqs": {
        "hook_strength": 20,
        "time_to_value": 12,
        "pacing_density": 10,
        "rewatch_loop_design": 8,
        "caption_readability": 8,
        "audio_strategy_fit": 7,
        "cta_quality": 6,
        "metadata_relevance": 7,
        "originality_authenticity": 10,
        "technical_quality": 7,
        "safety_compliance": 5,
    },
    "final_vps": {"pqs_weight": 0.55, "eps_weight": 0.45},
}


def _load_weights() -> dict:
    cfg = Path(__file__).resolve().parents[1] / "config" / "viral_scoring_weights.json"
    if not cfg.exists():
        return _DEFAULT_WEIGHTS

    try:
        data = json.loads(cfg.read_text())
    except Exception:
        return _DEFAULT_WEIGHTS

    pqs = data.get("pqs", {})
    final = data.get("final_vps", {})
    return {
        "pqs": {**_DEFAULT_WEIGHTS["pqs"], **pqs},
        "final_vps": {**_DEFAULT_WEIGHTS["final_vps"], **final},
    }


def _bounded(value: float) -> int:
    return max(0, min(100, round(value)))


def score_reel_plan(plan: ReelPlan) -> PlanScore:
    weights = _load_weights()["pqs"]

    hook_strength = 85 if len(plan.hook.text) >= 20 else 70
    if any(ch.isdigit() for ch in plan.hook.text):
        hook_strength = min(95, hook_strength + 4)

    # proxy for time-to-value based on hook duration in dry-run mode
    time_to_value = 95 if plan.hook.duration_sec <= 2.0 else 80 if plan.hook.duration_sec <= 3.0 else 65
    pacing_density = 88 if plan.cuts.target_pace == "fast" else 76
    rewatch_loop_design = 80 if "part 2" in plan.cta.lower() or "checklist" in plan.cta.lower() else 68
    caption_readability = 86 if plan.captions.words_per_line <= 4 else 74
    audio_strategy_fit = 78
    cta_quality = 84 if any(x in plan.cta.lower() for x in ["save", "comment", "follow", "test"]) else 70
    metadata_relevance = 80
    originality_authenticity = 82
    technical_quality = 82
    safety_compliance = 95

    features = {
        "hook_strength": hook_strength,
        "time_to_value": time_to_value,
        "pacing_density": pacing_density,
        "rewatch_loop_design": rewatch_loop_design,
        "caption_readability": caption_readability,
        "audio_strategy_fit": audio_strategy_fit,
        "cta_quality": cta_quality,
        "metadata_relevance": metadata_relevance,
        "originality_authenticity": originality_authenticity,
        "technical_quality": technical_quality,
        "safety_compliance": safety_compliance,
    }

    weighted_total = sum(features[k] * (weights[k] / 100) for k in features)
    total = _bounded(weighted_total)

    notes: list[str] = []
    if plan.duration_target_sec > 35:
        notes.append("Longer than typical viral short-form range; tighten to <=30s when possible.")
    if plan.captions.words_per_line > 5:
        notes.append("Caption lines may feel dense on mobile.")
    if "save" not in plan.cta.lower() and "comment" not in plan.cta.lower():
        notes.append("CTA may be weak for engagement actions.")

    return PlanScore(
        total=total,
        hook_strength=hook_strength,
        pacing=pacing_density,
        caption_clarity=caption_readability,
        cta_strength=cta_quality,
        notes=notes,
    )


def build_score_report(plan: ReelPlan, score: PlanScore) -> ScoreReport:
    weights = _load_weights()["pqs"]

    contribs = [
        FeatureContribution(
            feature="hook_strength",
            value=score.hook_strength,
            weight=weights["hook_strength"],
            contribution=round(score.hook_strength * (weights["hook_strength"] / 100), 2),
        ),
        FeatureContribution(
            feature="pacing_density",
            value=score.pacing,
            weight=weights["pacing_density"],
            contribution=round(score.pacing * (weights["pacing_density"] / 100), 2),
        ),
        FeatureContribution(
            feature="caption_readability",
            value=score.caption_clarity,
            weight=weights["caption_readability"],
            contribution=round(score.caption_clarity * (weights["caption_readability"] / 100), 2),
        ),
        FeatureContribution(
            feature="cta_quality",
            value=score.cta_strength,
            weight=weights["cta_quality"],
            contribution=round(score.cta_strength * (weights["cta_quality"] / 100), 2),
        ),
    ]

    failed_gates: list[str] = []
    if plan.hook.duration_sec > 6:
        failed_gates.append("time_to_value")

    recommendations = [
        Recommendation(priority="high", action="Trim intro so core value lands by <=2s", expected_lift_range="+8% to +20% retention"),
        Recommendation(priority="medium", action="Increase caption contrast and safe-zone spacing", expected_lift_range="+3% to +9% completion"),
    ]

    # EPS is placeholder in current dry-run pipeline
    eps = 0.0
    weights_final = _load_weights()["final_vps"]
    vps = _bounded((score.total * weights_final["pqs_weight"]) + (eps * weights_final["eps_weight"]))

    return ScoreReport(
        pqs=float(score.total),
        eps=eps,
        vps=float(vps),
        feature_contributions=contribs,
        failed_gates=failed_gates,
        recommendations=recommendations,
    )


def build_edit_suggestions(plan: ReelPlan) -> EditSuggestions:
    suggestions = [
        EditSuggestion(priority="high", action="trim_intro_to <=2.0s", timestamp_hint="0.0-2.0s"),
        EditSuggestion(priority="medium", action="insert_pattern_interrupt", timestamp_hint="~1.2s"),
        EditSuggestion(priority="medium", action="move_cta_after_value_proof", timestamp_hint=">=4.0s"),
    ]

    if plan.captions.words_per_line > 4:
        suggestions.append(EditSuggestion(priority="low", action="reduce_caption_words_per_line_to_4", timestamp_hint="global"))

    return EditSuggestions(suggestions=suggestions)
