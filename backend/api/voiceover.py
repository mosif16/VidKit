"""Voiceover API — generate and manage narration for projects."""
from __future__ import annotations
import os, json
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from backend.api._state import projects
from backend.api.project import _get_project
from backend.core.voice import generate_speech, list_voice_samples, VOICE_SAMPLES_DIR

router = APIRouter()

# Load primary voice template defaults
_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "voice_templates", "primary.json"
)
_DEFAULT_EXAG = 0.7
_DEFAULT_CFG = 0.5
_DEFAULT_VOICE: str | None = None
if os.path.exists(_TEMPLATE_PATH):
    try:
        with open(_TEMPLATE_PATH) as f:
            _tpl = json.load(f)
            _DEFAULT_EXAG = _tpl.get("parameters", {}).get("exaggeration", 0.7)
            _DEFAULT_CFG = _tpl.get("parameters", {}).get("cfg_weight", 0.5)
            ref = _tpl.get("reference_sample")
            if isinstance(ref, str) and ref.strip():
                _DEFAULT_VOICE = os.path.splitext(os.path.basename(ref.strip()))[0]
    except Exception:
        pass


class VoiceoverRequest(BaseModel):
    text: str | None = None  # None = use transcript text
    voice: str | None = None  # voice sample name, None = first available
    exaggeration: float = _DEFAULT_EXAG
    cfg_weight: float = _DEFAULT_CFG
    voiceover_volume: float = 1.0
    original_audio_volume: float = 0.0


class VoiceoverVolumeRequest(BaseModel):
    voiceover_volume: float = 1.0
    original_audio_volume: float = 0.0


@router.post("/project/{project_id}/voiceover")
async def generate_voiceover(project_id: str, req: VoiceoverRequest):
    """Generate voiceover narration for a project."""
    project = _get_project(project_id)

    # Determine text
    text = req.text
    if not text:
        # Build from transcript
        words = []
        for scene in project.scenes:
            for w in scene.transcript:
                if not w.is_filler:
                    words.append(w.word)
        text = " ".join(words).strip()
    
    if not text:
        raise HTTPException(400, "No text provided and no transcript available")

    # Find voice sample
    samples = list_voice_samples()
    voice_path = None
    selected_voice_name = req.voice

    if req.voice:
        match = next((s for s in samples if s["name"] == req.voice), None)
        if not match:
            raise HTTPException(404, f"Voice '{req.voice}' not found")
        voice_path = match["path"]
    else:
        # Prefer template-configured default voice, then fallback to first available.
        if _DEFAULT_VOICE:
            match = next((s for s in samples if s["name"] == _DEFAULT_VOICE), None)
            if match:
                voice_path = match["path"]
                selected_voice_name = _DEFAULT_VOICE
        if voice_path is None and samples:
            voice_path = samples[0]["path"]
            selected_voice_name = samples[0]["name"]

    # Generate output path in project directory
    from backend.api._state import PROJECTS_DIR
    proj_dir = os.path.join(PROJECTS_DIR, project_id)
    os.makedirs(proj_dir, exist_ok=True)
    output_path = os.path.join(proj_dir, "voiceover.wav")

    # For long text, split into chunks and concatenate
    # Chatterbox works best with shorter sentences
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    # Group sentences into chunks of ~100 chars each for natural pacing
    chunks = []
    current_chunk = ""
    for s in sentences:
        if len(current_chunk) + len(s) > 120 and current_chunk:
            chunks.append(current_chunk.strip())
            current_chunk = s
        else:
            current_chunk = (current_chunk + " " + s).strip()
    if current_chunk:
        chunks.append(current_chunk.strip())

    if len(chunks) <= 1:
        # Single generation
        result = generate_speech(
            text=text,
            voice_sample_path=voice_path,
            output_path=output_path,
            exaggeration=req.exaggeration,
            cfg_weight=req.cfg_weight,
        )
        if result["status"] == "error":
            raise HTTPException(500, result["message"])
    else:
        # Multi-chunk: generate each, then concatenate with ffmpeg
        import subprocess, tempfile
        chunk_paths = []
        for i, chunk in enumerate(chunks):
            chunk_path = os.path.join(proj_dir, f"vo_chunk_{i:03d}.wav")
            result = generate_speech(
                text=chunk,
                voice_sample_path=voice_path,
                output_path=chunk_path,
                exaggeration=req.exaggeration,
                cfg_weight=req.cfg_weight,
            )
            if result["status"] == "error":
                # Clean up chunks
                for p in chunk_paths:
                    if os.path.exists(p):
                        os.remove(p)
                raise HTTPException(500, f"Chunk {i} failed: {result['message']}")
            chunk_paths.append(chunk_path)
        
        # Concatenate chunks
        concat_list = os.path.join(proj_dir, "vo_concat.txt")
        with open(concat_list, "w") as f:
            for p in chunk_paths:
                f.write(f"file '{p}'\n")
        
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1",
            output_path
        ], capture_output=True, timeout=60)
        
        # Clean up chunks
        for p in chunk_paths:
            if os.path.exists(p):
                os.remove(p)
        if os.path.exists(concat_list):
            os.remove(concat_list)
        
        # Get final duration
        probe = subprocess.run([
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "csv=p=0", output_path
        ], capture_output=True, text=True, timeout=10)
        duration = float(probe.stdout.strip()) if probe.stdout.strip() else 0
        result = {"status": "ok", "model": "original", "output_path": output_path, 
                  "duration": round(duration, 2), "chunks": len(chunks)}

    # Update project
    project.voiceover_path = output_path
    project.voiceover_text = text
    project.voiceover_voice = selected_voice_name or "default"
    project.voiceover_volume = req.voiceover_volume
    project.original_audio_volume = req.original_audio_volume

    return {
        "status": "ok",
        "voiceover_path": output_path,
        "duration": result.get("duration", 0),
        "text_length": len(text),
        "chunks": result.get("chunks", 1),
        "voice": selected_voice_name or "default",
        "model": result.get("model", "original"),
    }


@router.get("/project/{project_id}/voiceover")
async def get_voiceover_status(project_id: str):
    """Get voiceover status for a project."""
    project = _get_project(project_id)
    has_voiceover = bool(project.voiceover_path and os.path.exists(project.voiceover_path))
    
    return {
        "has_voiceover": has_voiceover,
        "voiceover_text": project.voiceover_text,
        "voiceover_voice": project.voiceover_voice,
        "voiceover_volume": project.voiceover_volume,
        "original_audio_volume": project.original_audio_volume,
    }


@router.get("/project/{project_id}/voiceover/audio")
async def get_voiceover_audio(project_id: str):
    """Stream the voiceover audio file."""
    project = _get_project(project_id)
    if not project.voiceover_path or not os.path.exists(project.voiceover_path):
        raise HTTPException(404, "No voiceover generated yet")
    return FileResponse(project.voiceover_path, media_type="audio/wav")


@router.post("/project/{project_id}/voiceover/volume")
async def update_voiceover_volume(project_id: str, req: VoiceoverVolumeRequest):
    """Update voiceover and original audio volume levels."""
    project = _get_project(project_id)
    project.voiceover_volume = max(0.0, min(2.0, req.voiceover_volume))
    project.original_audio_volume = max(0.0, min(1.0, req.original_audio_volume))
    return {
        "status": "ok",
        "voiceover_volume": project.voiceover_volume,
        "original_audio_volume": project.original_audio_volume,
    }


@router.delete("/project/{project_id}/voiceover")
async def delete_voiceover(project_id: str):
    """Remove voiceover from a project."""
    project = _get_project(project_id)
    if project.voiceover_path and os.path.exists(project.voiceover_path):
        os.remove(project.voiceover_path)
    project.voiceover_path = ""
    project.voiceover_text = ""
    project.voiceover_voice = ""
    return {"status": "ok"}
