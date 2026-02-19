from __future__ import annotations

from .models import AgentReelRequest, ReelPlan, HookPlan, CaptionPlan, CutPlan


def _base_hook(platform: str) -> str:
    return {
        "reels": "Stop scrolling — watch this before your next post",
        "tiktok": "POV: You fix your reel in 20 seconds",
        "shorts": "This one tweak can double watch-time",
    }.get(platform, "Watch this first")


def create_reel_plan(req: AgentReelRequest) -> ReelPlan:
    return ReelPlan(
        id="base",
        template=req.template,
        platform=req.platform,
        objective=req.objective,
        duration_target_sec=req.duration_target_sec,
        hook=HookPlan(
            text=_base_hook(req.platform),
            style="bold-top",
            duration_sec=2.5,
        ),
        captions=CaptionPlan(
            strategy="kinetic-subtitles",
            words_per_line=4,
            emphasis="verbs+numbers",
        ),
        cuts=CutPlan(
            strategy="hook-fast-middle-accelerate-cta",
            target_pace="fast",
            scene_count_target=max(4, min(10, req.duration_target_sec // 3)),
        ),
        cta="Save this and try it on your next edit",
    )


def create_candidate_plans(req: AgentReelRequest) -> list[ReelPlan]:
    base = create_reel_plan(req)
    variants = [
        {
            "id": "v1",
            "hook": base.hook.text,
            "cta": "Save this and try it on your next edit",
            "pace": "fast",
            "wpl": 4,
        },
        {
            "id": "v2",
            "hook": "3 mistakes killing your engagement (fix this now)",
            "cta": "Comment 'template' and I’ll send the structure",
            "pace": "fast",
            "wpl": 3,
        },
        {
            "id": "v3",
            "hook": "If your reel retention drops, do this first",
            "cta": "Save this checklist before your next post",
            "pace": "medium",
            "wpl": 4,
        },
        {
            "id": "v4",
            "hook": "The 20-second edit loop top creators repeat",
            "cta": "Follow for part 2 with live examples",
            "pace": "fast",
            "wpl": 5,
        },
        {
            "id": "v5",
            "hook": "You’re one hook away from a better reel",
            "cta": "Test this today and compare watch-time",
            "pace": "fast",
            "wpl": 4,
        },
    ]

    plans: list[ReelPlan] = []
    for v in variants[: req.candidates]:
        plans.append(
            ReelPlan(
                id=v["id"],
                template=req.template,
                platform=req.platform,
                objective=req.objective,
                duration_target_sec=req.duration_target_sec,
                hook=HookPlan(text=v["hook"], style="bold-top", duration_sec=2.3),
                captions=CaptionPlan(
                    strategy="kinetic-subtitles",
                    words_per_line=v["wpl"],
                    emphasis="verbs+numbers",
                ),
                cuts=CutPlan(
                    strategy="hook-fast-middle-accelerate-cta",
                    target_pace=v["pace"],
                    scene_count_target=max(4, min(10, req.duration_target_sec // 3)),
                ),
                cta=v["cta"],
            )
        )

    return plans
