"""Content analysis endpoints — hook detection, engagement scoring, auto-edit."""
from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from backend.core.content_analyzer import (
    analyze_hook, analyze_pacing, score_engagement, auto_edit_for_platform,
    PLATFORM_TARGETS,
)
from backend.models import Edit, EditKind
from backend.edit.engine import apply_edit
from backend.api._state import projects, PROJECTS_DIR
import os

router = APIRouter()


class AutoEditRequest(BaseModel):
    platform: str = "reels"  # tiktok, reels, shorts, any
    apply: bool = False  # if True, apply edits; if False, just suggest


@router.get("/project/{project_id}/analyze")
async def analyze_content(project_id: str, platform: str = "any"):
    """Full content analysis — hook, pacing, engagement score."""
    proj = _get_project(project_id)
    
    hook = analyze_hook(proj)
    pacing = analyze_pacing(proj)
    engagement = score_engagement(proj, platform)
    
    total_dur = sum(s.duration for s in proj.scenes)
    
    return {
        "hook": {
            "has_speech_in_3s": hook.has_speech_in_3s,
            "first_word_time": hook.first_word_time,
            "hook_text": hook.hook_text,
            "score": hook.hook_score,
            "suggestion": hook.suggestion,
        },
        "pacing": {
            "words_per_minute": round(pacing.words_per_minute, 1),
            "dead_air_seconds": round(pacing.dead_air_seconds, 1),
            "dead_air_pct": round(pacing.dead_air_pct * 100, 1),
            "longest_pause": round(pacing.longest_pause, 1),
            "repetition_score": round(pacing.repetition_score, 2),
            "suggestion": pacing.suggestion,
        },
        "engagement": {
            "score": round(engagement.overall),
            "breakdown": engagement.breakdown,
            "caption_ready": engagement.caption_ready,
        },
        "duration": round(total_dur, 1),
        "platform_target": PLATFORM_TARGETS.get(platform, PLATFORM_TARGETS["any"]),
    }


@router.post("/project/{project_id}/auto-edit")
async def auto_edit(project_id: str, req: AutoEditRequest):
    """Auto-edit video for a specific platform using content-aware rules."""
    proj = _get_project(project_id)
    
    suggestions = auto_edit_for_platform(proj, req.platform)
    
    if not req.apply:
        return {
            "status": "preview",
            "platform": req.platform,
            "suggested_edits": suggestions,
            "current_duration": round(sum(s.duration for s in proj.scenes), 1),
            "target": PLATFORM_TARGETS.get(req.platform, PLATFORM_TARGETS["any"]),
        }
    
    # Apply all edits
    applied = []
    for suggestion in suggestions:
        try:
            edit = Edit(
                kind=EditKind(suggestion["kind"]),
                target_scene_id=suggestion.get("target_scene_id", ""),
                params=suggestion.get("params", {}),
            )
            proj = apply_edit(proj, edit)
            applied.append(suggestion)
        except Exception as e:
            applied.append({"error": str(e), **suggestion})
    
    projects[project_id] = proj
    _save(proj)
    
    new_dur = sum(s.duration for s in proj.scenes)
    
    return {
        "status": "ok",
        "platform": req.platform,
        "applied": applied,
        "scene_count": len(proj.scenes),
        "new_duration": round(new_dur, 1),
    }


def _get_project(project_id: str):
    from backend.api.project import _get_project as gp
    return gp(project_id)


def _save(proj):
    path = os.path.join(PROJECTS_DIR, proj.id, "project.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    proj.save(path)
