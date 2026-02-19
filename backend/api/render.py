"""Render endpoints."""
from __future__ import annotations
import os
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from backend.models import RenderPreset
from backend.render.ffmpeg import render, render_preview_frames
from backend.api._state import projects, PROJECTS_DIR

router = APIRouter()


class RenderRequest(BaseModel):
    preset: str = "original"  # original, tiktok, youtube, square
    output_filename: Optional[str] = None
    captions: bool = False  # burn in word-by-word captions
    caption_style: str = "default"  # default, bold, minimal


@router.post("/project/{project_id}/render")
async def render_project(project_id: str, req: RenderRequest, background_tasks: BackgroundTasks):
    """Start rendering the project."""
    proj = _get_project(project_id)

    if proj.status == "rendering":
        raise HTTPException(409, "Already rendering")

    # Determine preset
    presets = {
        "tiktok": RenderPreset.tiktok(),
        "youtube": RenderPreset.youtube(),
        "square": RenderPreset.square(),
        "original": RenderPreset.original(proj.width, proj.height, int(proj.fps)),
    }
    preset = presets.get(req.preset)

    filename = req.output_filename or f"{proj.name}_edited.mp4"
    output_path = os.path.join(PROJECTS_DIR, proj.id, filename)

    proj.status = "rendering"
    projects[project_id] = proj

    burn_captions = req.captions
    cap_style = req.caption_style

    async def do_render():
        try:
            render(proj, output_path, preset=preset,
                   burn_captions=burn_captions, caption_style=cap_style)
            proj.status = "done"
        except Exception as e:
            proj.status = "error"
            proj.error = str(e)
        projects[project_id] = proj
        _save(proj)

    background_tasks.add_task(do_render)

    return {"status": "rendering", "output": filename}


@router.get("/project/{project_id}/render/status")
async def render_status(project_id: str):
    """Check render status."""
    proj = _get_project(project_id)
    return {"status": proj.status, "error": proj.error}


@router.get("/project/{project_id}/render/download")
async def download_render(project_id: str):
    """Download the rendered video."""
    proj = _get_project(project_id)
    proj_dir = os.path.join(PROJECTS_DIR, proj.id)
    
    # Find rendered files
    source_name = os.path.basename(proj.source_path or "")
    for f in sorted(os.listdir(proj_dir)):
        if f.endswith("_edited.mp4"):
            return FileResponse(os.path.join(proj_dir, f), filename=f, media_type="video/mp4")

    for f in sorted(os.listdir(proj_dir)):
        if f.endswith(".mp4") and f != source_name:
            return FileResponse(os.path.join(proj_dir, f), filename=f, media_type="video/mp4")

    raise HTTPException(404, "No rendered video found")


@router.get("/project/{project_id}/preview")
async def get_preview_frames(project_id: str, count: int = 10):
    """Get preview frames from the edited timeline."""
    proj = _get_project(project_id)
    preview_dir = os.path.join(PROJECTS_DIR, proj.id, "previews")
    frames = render_preview_frames(proj, preview_dir, count=count)
    return {"frames": [f"/project/{project_id}/preview/{os.path.basename(f)}" for f in frames]}


@router.get("/project/{project_id}/preview/{filename}")
async def get_preview_frame(project_id: str, filename: str):
    """Get a single preview frame."""
    path = os.path.join(PROJECTS_DIR, project_id, "previews", filename)
    if not os.path.exists(path):
        raise HTTPException(404, "Frame not found")
    return FileResponse(path, media_type="image/jpeg")


def _get_project(project_id: str):
    from backend.api.project import _get_project as gp
    return gp(project_id)


def _save(proj):
    path = os.path.join(PROJECTS_DIR, proj.id, "project.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    proj.save(path)
