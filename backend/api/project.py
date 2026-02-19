"""Project CRUD endpoints."""
from __future__ import annotations
import os, glob
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from backend.models import Project
from backend.api._state import projects, PROJECTS_DIR

router = APIRouter()


def _summary_from_pending(pid: str, pending: dict) -> dict:
    return {
        "id": pid,
        "name": pending.get("name", pid),
        "status": pending.get("status", "analyzing"),
        "duration": pending.get("duration", 0.0),
        "scene_count": pending.get("scene_count", 0),
        "error": pending.get("error", ""),
    }


@router.get("/projects")
async def list_projects():
    """List all projects."""
    result = []

    # In-memory projects first
    for pid, proj in projects.items():
        if isinstance(proj, Project):
            result.append({
                "id": proj.id,
                "name": proj.name,
                "status": proj.status,
                "duration": proj.duration,
                "scene_count": len(proj.scenes),
                "error": proj.error,
            })
        elif isinstance(proj, dict):
            result.append(_summary_from_pending(pid, proj))
        elif proj is None:
            result.append(_summary_from_pending(pid, {"status": "analyzing"}))

    # Also scan disk for saved projects
    for pjson in glob.glob(os.path.join(PROJECTS_DIR, "*", "project.json")):
        proj = Project.load(pjson)
        if proj.id not in projects:
            projects[proj.id] = proj
            result.append({
                "id": proj.id,
                "name": proj.name,
                "status": proj.status,
                "duration": proj.duration,
                "scene_count": len(proj.scenes),
                "error": proj.error,
            })

    return {"projects": result}


@router.get("/project/{project_id}")
async def get_project(project_id: str):
    """Get full project details including scene map."""
    proj = _get_project(project_id)
    return proj.to_dict()


@router.get("/project/{project_id}/source")
async def get_source_video(project_id: str):
    """Stream the original source video for playback."""
    proj = _get_project(project_id)
    if not proj.source_path or not os.path.exists(proj.source_path):
        raise HTTPException(404, "Source video not found")
    return FileResponse(proj.source_path, media_type="video/mp4")


@router.get("/project/{project_id}/thumbnail/{scene_id}")
async def get_thumbnail(project_id: str, scene_id: str):
    """Get scene thumbnail image."""
    proj = _get_project(project_id)
    scene = next((s for s in proj.scenes if s.id == scene_id), None)
    if not scene or not scene.thumbnail_path or not os.path.exists(scene.thumbnail_path):
        raise HTTPException(404, "Thumbnail not found")
    return FileResponse(scene.thumbnail_path, media_type="image/jpeg")


def _get_project(project_id: str) -> Project:
    if project_id in projects:
        proj = projects[project_id]
        if isinstance(proj, Project):
            return proj
        if isinstance(proj, dict):
            status = proj.get("status", "analyzing")
            if status == "error":
                raise HTTPException(500, proj.get("error", "Project analysis failed"))
            raise HTTPException(202, "Project is still analyzing")
        if proj is None:
            raise HTTPException(202, "Project is still analyzing")

    # Try loading from disk
    path = os.path.join(PROJECTS_DIR, project_id, "project.json")
    if os.path.exists(path):
        proj = Project.load(path)
        projects[project_id] = proj
        return proj

    raise HTTPException(404, "Project not found")
