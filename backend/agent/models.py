from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

Platform = Literal["reels", "tiktok", "shorts"]


class AgentReelRequest(BaseModel):
    source_video: str = Field(..., description="Path or project video id")
    template: str = Field(default="viral-hook-v1", description="Editing template/style slug")
    platform: Platform = "reels"
    objective: str = Field(default="maximize watch-time and shares")
    duration_target_sec: int = Field(default=20, ge=8, le=60)
    tone: str = Field(default="high-energy")
    candidates: int = Field(default=3, ge=1, le=5)


class HookPlan(BaseModel):
    text: str
    style: str = "bold-top"
    duration_sec: float = 2.5


class CaptionPlan(BaseModel):
    strategy: str
    words_per_line: int = 4
    emphasis: str = "keywords"


class CutPlan(BaseModel):
    strategy: str
    target_pace: str
    scene_count_target: int


class ReelPlan(BaseModel):
    id: str = "base"
    template: str
    platform: Platform
    objective: str
    duration_target_sec: int
    hook: HookPlan
    captions: CaptionPlan
    cuts: CutPlan
    cta: str


class PlanScore(BaseModel):
    total: int
    hook_strength: int
    pacing: int
    caption_clarity: int
    cta_strength: int
    notes: list[str] = Field(default_factory=list)


class FeatureContribution(BaseModel):
    feature: str
    value: float
    weight: float
    contribution: float


class Recommendation(BaseModel):
    priority: Literal["high", "medium", "low"]
    action: str
    expected_lift_range: str


class ScoreReport(BaseModel):
    pqs: float
    eps: float
    vps: float
    feature_contributions: list[FeatureContribution]
    failed_gates: list[str] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)


class EditSuggestion(BaseModel):
    priority: Literal["high", "medium", "low"]
    action: str
    timestamp_hint: str


class EditSuggestions(BaseModel):
    suggestions: list[EditSuggestion] = Field(default_factory=list)


class PipelineStageResult(BaseModel):
    stage: str
    status: Literal["ok", "warning", "todo"]
    detail: str


class ExecutionReport(BaseModel):
    dry_run: bool = True
    stages: list[PipelineStageResult]
    next_actions: list[str]


class AgentReelResponse(BaseModel):
    status: Literal["ok"] = "ok"
    plan: ReelPlan
    score: PlanScore
    score_report: ScoreReport
    edit_suggestions: EditSuggestions
    candidates: list[ReelPlan] = Field(default_factory=list)
    execution: ExecutionReport
