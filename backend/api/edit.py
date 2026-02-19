"""Edit endpoints."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from backend.models import Edit, EditKind
from backend.edit.engine import apply_edit, delete_dead_air, add_fade_transitions
from backend.edit.transcript import delete_text_range, delete_all_filler_words
from backend.api._state import projects, PROJECTS_DIR
import os

router = APIRouter()


class EditRequest(BaseModel):
    kind: str
    target_scene_id: str = ""
    params: dict = Field(default_factory=dict)


class TranscriptDeleteRequest(BaseModel):
    start_time: float
    end_time: float


@router.post("/project/{project_id}/edit")
async def edit_project(project_id: str, req: EditRequest):
    proj = _get_project(project_id)
    try:
        edit = Edit(kind=EditKind(req.kind), target_scene_id=req.target_scene_id, params=req.params)
    except ValueError:
        raise HTTPException(400, f"Unknown edit kind: {req.kind}")

    proj = apply_edit(proj, edit)
    projects[project_id] = proj
    _save(proj)
    return {"status": "ok", "scene_count": len(proj.scenes)}


@router.post("/project/{project_id}/delete-dead-air")
async def remove_dead_air(project_id: str):
    proj = _get_project(project_id)
    proj = delete_dead_air(proj)
    projects[project_id] = proj
    _save(proj)
    return {"status": "ok", "scene_count": len(proj.scenes)}


@router.post("/project/{project_id}/delete-filler-words")
async def remove_filler_words(project_id: str):
    proj = _get_project(project_id)
    proj = delete_all_filler_words(proj)
    projects[project_id] = proj
    _save(proj)
    return {"status": "ok", "scene_count": len(proj.scenes)}


@router.post("/project/{project_id}/delete-text-range")
async def remove_text_range(project_id: str, req: TranscriptDeleteRequest):
    proj = _get_project(project_id)
    proj = delete_text_range(proj, req.start_time, req.end_time)
    projects[project_id] = proj
    _save(proj)
    return {"status": "ok", "scene_count": len(proj.scenes)}


@router.post("/project/{project_id}/add-fade-transitions")
async def fade_all(project_id: str):
    proj = _get_project(project_id)
    proj = add_fade_transitions(proj)
    projects[project_id] = proj
    _save(proj)
    return {"status": "ok", "scene_count": len(proj.scenes)}


@router.post("/project/{project_id}/undo")
async def undo_last_edit(project_id: str):
    proj = _get_project(project_id)
    success = proj.undo()
    if not success:
        raise HTTPException(400, "Nothing to undo")
    projects[project_id] = proj
    _save(proj)
    return {"status": "ok", "scene_count": len(proj.scenes), "edits_remaining": len(proj.edits)}


def _get_project(project_id: str):
    from backend.api.project import _get_project as gp
    return gp(project_id)


def _save(proj):
    path = os.path.join(PROJECTS_DIR, proj.id, "project.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    proj.save(path)
