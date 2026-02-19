from __future__ import annotations

from .models import (
    AgentReelRequest,
    AgentReelResponse,
    ExecutionReport,
    PipelineStageResult,
    ReelPlan,
)
from .planner import create_candidate_plans
from .scorer import score_reel_plan


def _pick_best(plans: list[ReelPlan]) -> tuple[ReelPlan, dict[str, int]]:
    scored = {p.id: score_reel_plan(p).total for p in plans}
    best_id = max(scored, key=scored.get)
    best_plan = next(p for p in plans if p.id == best_id)
    return best_plan, scored


def run_agent_reel_dry_run(req: AgentReelRequest) -> AgentReelResponse:
    candidates = create_candidate_plans(req)
    best_plan, ranked = _pick_best(candidates)
    score = score_reel_plan(best_plan)

    stages = [
        PipelineStageResult(stage="ingest", status="ok", detail=f"Accepted source: {req.source_video}"),
        PipelineStageResult(stage="creative-plan", status="ok", detail=f"Generated {len(candidates)} candidate reel plans"),
        PipelineStageResult(stage="rank", status="ok", detail=f"Selected {best_plan.id} with score {score.total} (rankings: {ranked})"),
        PipelineStageResult(stage="timeline-build", status="todo", detail="TODO: map actual detected scenes to selected beat plan"),
        PipelineStageResult(stage="render", status="todo", detail="TODO: execute selected candidate in production render pipeline"),
    ]

    execution = ExecutionReport(
        dry_run=True,
        stages=stages,
        next_actions=[
            "Connect scene detector output to cut selection",
            "Bind selected plan to automatic edit operations",
            "Run A/B score loop with real retention metrics",
        ],
    )

    return AgentReelResponse(plan=best_plan, score=score, candidates=candidates, execution=execution)
