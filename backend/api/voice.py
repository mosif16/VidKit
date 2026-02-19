"""Voice cloning API endpoints."""
from __future__ import annotations
import os, shutil
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from backend.core.voice import generate_speech, list_voice_samples, VOICE_SAMPLES_DIR, OUTPUT_DIR

router = APIRouter()


class TTSRequest(BaseModel):
    text: str
    voice: str | None = None  # name of saved voice sample, or None for default
    exaggeration: float = 0.7
    cfg_weight: float = 0.5


@router.post("/tts/generate")
async def tts_generate(req: TTSRequest):
    """Generate speech from text with optional voice cloning."""
    voice_path = None
    if req.voice:
        # Look up saved voice sample
        samples = list_voice_samples()
        match = next((s for s in samples if s["name"] == req.voice), None)
        if match:
            voice_path = match["path"]
        else:
            raise HTTPException(404, f"Voice sample '{req.voice}' not found")
    
    result = generate_speech(
        text=req.text,
        voice_sample_path=voice_path,
        exaggeration=req.exaggeration,
        cfg_weight=req.cfg_weight,
    )
    
    if result["status"] == "error":
        raise HTTPException(500, result["message"])
    
    return result


@router.post("/tts/voices/upload")
async def upload_voice_sample(
    file: UploadFile = File(...),
    name: str = Form(...),
):
    """Upload a voice sample for cloning."""
    ext = os.path.splitext(file.filename or "audio.wav")[1]
    if ext not in (".wav", ".mp3", ".m4a", ".flac"):
        raise HTTPException(400, "Unsupported audio format. Use WAV, MP3, M4A, or FLAC.")
    
    save_path = os.path.join(VOICE_SAMPLES_DIR, f"{name}{ext}")
    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    return {"status": "ok", "name": name, "path": save_path}


@router.get("/tts/voices")
async def get_voices():
    """List available voice samples."""
    return {"voices": list_voice_samples()}


@router.delete("/tts/voices/{name}")
async def delete_voice(name: str):
    """Delete a saved voice sample."""
    samples = list_voice_samples()
    match = next((s for s in samples if s["name"] == name), None)
    if not match:
        raise HTTPException(404, f"Voice '{name}' not found")
    os.remove(match["path"])
    return {"status": "ok", "deleted": name}
