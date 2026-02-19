from __future__ import annotations

from .models import ReelPlan, PlanScore


def score_reel_plan(plan: ReelPlan) -> PlanScore:
    hook_strength = 85 if len(plan.hook.text) >= 20 else 70
    if any(ch.isdigit() for ch in plan.hook.text):
        hook_strength = min(95, hook_strength + 4)

    pacing = 88 if plan.cuts.target_pace == "fast" else 76
    caption_clarity = 86 if plan.captions.words_per_line <= 4 else 74
    cta_strength = 84 if any(x in plan.cta.lower() for x in ["save", "comment", "follow", "test"]) else 70

    total = round((hook_strength * 0.33) + (pacing * 0.27) + (caption_clarity * 0.2) + (cta_strength * 0.2))

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
        pacing=pacing,
        caption_clarity=caption_clarity,
        cta_strength=cta_strength,
        notes=notes,
    )
