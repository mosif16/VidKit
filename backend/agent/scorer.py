from __future__ import annotations

from .models import ReelPlan, PlanScore


def score_reel_plan(plan: ReelPlan) -> PlanScore:
    hook_strength = 85 if len(plan.hook.text) >= 20 else 70
    pacing = 88 if plan.cuts.target_pace == "fast" else 72
    caption_clarity = 84 if plan.captions.words_per_line <= 5 else 68
    cta_strength = 82 if "Save" in plan.cta or "save" in plan.cta else 70

    total = round((hook_strength * 0.35) + (pacing * 0.3) + (caption_clarity * 0.2) + (cta_strength * 0.15))

    notes: list[str] = []
    if plan.duration_target_sec > 35:
        notes.append("Longer than typical viral short-form range; tighten to <=30s when possible.")
    if plan.captions.words_per_line > 5:
        notes.append("Caption lines may feel dense on mobile.")

    return PlanScore(
        total=total,
        hook_strength=hook_strength,
        pacing=pacing,
        caption_clarity=caption_clarity,
        cta_strength=cta_strength,
        notes=notes,
    )
