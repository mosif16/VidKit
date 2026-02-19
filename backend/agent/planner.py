from __future__ import annotations

from .models import AgentReelRequest, ReelPlan, HookPlan, CaptionPlan, CutPlan


def create_reel_plan(req: AgentReelRequest) -> ReelPlan:
    hook_text = {
        "reels": "Stop scrolling — watch this before your next post",
        "tiktok": "POV: You fix your reel in 20 seconds",
        "shorts": "This one tweak can double watch-time",
    }.get(req.platform, "Watch this first")

    return ReelPlan(
        template=req.template,
        platform=req.platform,
        objective=req.objective,
        duration_target_sec=req.duration_target_sec,
        hook=HookPlan(
            text=hook_text,
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
