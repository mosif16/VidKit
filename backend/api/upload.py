"""Upload endpoint."""
from __future__ import annotations
import os, shutil, uuid, re, asyncio
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, BackgroundTasks
from backend.core.analyzer import analyze_video
from backend.api._state import projects, PROJECTS_DIR

router = APIRouter()


def _safe_filename(name: str) -> str:
    """Return a filesystem-safe filename with extension preserved."""
    base = Path(name).name  # strip any directory parts
    stem, ext = os.path.splitext(base)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    if not stem:
        stem = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    ext = ext.lower() if ext else ".mp4"
    return f"{stem}{ext}"


@router.post("/upload")
async def upload_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Upload a video file and start analysis."""
    project_id = uuid.uuid4().hex[:8]

    upload_dir = os.path.join(PROJECTS_DIR, "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    safe_name = _safe_filename(file.filename or "upload.mp4")
    stored_name = f"{project_id}---{safe_name}"
    file_path = os.path.join(upload_dir, stored_name)

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Track pending analysis with structured metadata
    projects[project_id] = {
        "id": project_id,
        "name": os.path.splitext(safe_name)[0],
        "status": "analyzing",
        "duration": 0.0,
        "scene_count": 0,
        "error": "",
        "source_path": file_path,
        "created_at": datetime.now().timestamp(),
    }

    async def run_analysis():
        try:
            project = await asyncio.wait_for(
                analyze_video(file_path, PROJECTS_DIR, project_id=project_id),
                timeout=900,
            )
            projects[project.id] = project
        except asyncio.TimeoutError:
            projects[project_id] = {
                **projects.get(project_id, {"id": project_id, "name": os.path.splitext(safe_name)[0]}),
                "status": "error",
                "error": "Analysis timed out after 15 minutes",
            }
        except Exception as e:
            projects[project_id] = {
                **projects.get(project_id, {"id": project_id, "name": os.path.splitext(safe_name)[0]}),
                "status": "error",
                "error": f"Analysis failed: {str(e)}",
            }

    background_tasks.add_task(run_analysis)

    return {
        "status": "analyzing",
        "project_id": project_id,
        "filename": safe_name,
        "stored_as": stored_name,
    }
