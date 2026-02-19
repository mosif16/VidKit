"""Agent Reel Engine endpoints."""
from __future__ import annotations

from fastapi import APIRouter
from backend.agent.models import AgentReelRequest, AgentReelResponse
from backend.agent.orchestrator import run_agent_reel_dry_run

router = APIRouter()


@router.post("/agent/reel", response_model=AgentReelResponse)
async def agent_reel(req: AgentReelRequest):
    """Create a dry-run autonomous reel plan + execution report.

    This endpoint intentionally does not run rendering yet.
    """
    return run_agent_reel_dry_run(req)
