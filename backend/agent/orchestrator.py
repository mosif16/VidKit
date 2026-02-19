from __future__ import annotations

from .models import (
    AgentReelRequest,
    AgentReelResponse,
    ExecutionReport,
    PipelineStageResult,
)
from .planner import create_reel_plan
from .scorer import score_reel_plan


def run_agent_reel_dry_run(req: AgentReelRequest) -> AgentReelResponse:
    plan = create_reel_plan(req)
    score = score_reel_plan(plan)

    stages = [
        PipelineStageResult(stage="ingest", status="ok", detail=f"Accepted source: {req.source_video}"),
        PipelineStageResult(stage="creative-plan", status="ok", detail=f"Template '{plan.template}' selected for {plan.platform}"),
        PipelineStageResult(stage="score", status="ok", detail=f"Initial virality score: {score.total}"),
        PipelineStageResult(stage="timeline-build", status="todo", detail="TODO: map actual detected scenes to planned cut strategy"),
        PipelineStageResult(stage="render", status="todo", detail="TODO: execute render + caption burn + voiceover in production pipeline"),
    ]

    execution = ExecutionReport(
        dry_run=True,
        stages=stages,
        next_actions=[
            "Connect scene detector output to cut selection",
            "Add multimodal ranking loop (video+audio+text)",
            "Run A/B scoring over multiple hooks and CTAs",
        ],
    )

    return AgentReelResponse(plan=plan, score=score, execution=execution)
