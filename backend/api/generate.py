"""Local generation endpoints (CogVideoX baseline)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.video_generation import generate_cogvideox, result_to_dict

router = APIRouter()


class LocalGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=3)
    output_name: Optional[str] = Field(default="cogvideox_local.mp4")
    model_id: str = Field(default="THUDM/CogVideoX-2b")
    num_inference_steps: int = Field(default=12, ge=4, le=64)
    num_frames: int = Field(default=24, ge=8, le=96)
    width: int = Field(default=720, ge=320, le=1280)
    height: int = Field(default=480, ge=240, le=1280)
    fps: int = Field(default=8, ge=4, le=30)


@router.post("/generate/local-video")
async def local_video_generate(req: LocalGenerateRequest):
    projects = Path(__file__).resolve().parents[2] / "projects" / "generated"
    projects.mkdir(parents=True, exist_ok=True)
    output_path = projects / req.output_name

    try:
        result = generate_cogvideox(
            prompt=req.prompt,
            output_path=output_path,
            model_id=req.model_id,
            num_inference_steps=req.num_inference_steps,
            num_frames=req.num_frames,
            width=req.width,
            height=req.height,
            fps=req.fps,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"local generation failed: {exc}")

    payload = result_to_dict(result)
    payload["relative_output"] = str(output_path)
    return payload
