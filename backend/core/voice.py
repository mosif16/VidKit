"""Voice cloning and TTS via Chatterbox.

Runs in a separate Python 3.11 venv (.venv-tts) because Chatterbox
pins numpy<1.26 and torch==2.6.0 which are incompatible with the main
Python 3.14 venv.

Usage: call generate_speech() which shells out to the TTS venv.
"""
from __future__ import annotations
import json, os, subprocess, tempfile, uuid

VIDKIT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TTS_VENV = os.path.join(VIDKIT_DIR, ".venv-tts")
TTS_PYTHON = os.path.join(TTS_VENV, "bin", "python3.11")
VOICE_SAMPLES_DIR = os.path.join(VIDKIT_DIR, "voice_samples")
OUTPUT_DIR = os.path.join(VIDKIT_DIR, "projects", "tts_output")

os.makedirs(VOICE_SAMPLES_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def generate_speech(
    text: str,
    voice_sample_path: str | None = None,
    output_path: str | None = None,
    exaggeration: float = 0.7,
    cfg_weight: float = 0.5,
) -> dict:
    """Generate speech from text, optionally cloning a voice.
    
    Args:
        text: Text to speak
        voice_sample_path: Path to WAV/MP3 reference audio for voice cloning (None = default voice)
        output_path: Where to save the output WAV (auto-generated if None)
        exaggeration: Emotional exaggeration (0.0-1.0, default 0.5)
        cfg_weight: Classifier-free guidance weight (0.0-1.0, default 0.5)
    
    Returns:
        dict with status, output_path, duration_seconds
    """
    if output_path is None:
        output_path = os.path.join(OUTPUT_DIR, f"tts_{uuid.uuid4().hex[:8]}.wav")
    
    # Build the TTS script to run in the 3.11 venv
    # Uses ORIGINAL model (not Turbo) — CFG produces higher quality output
    # Primary voice template: exag=0.7, cfg=0.5 (expressive + balanced guidance)
    script = f'''
import torch, torchaudio, time, json, warnings
warnings.filterwarnings("ignore")

# Patch watermarker (native ext doesn't build on ARM)
import perth
class NoopWatermarker:
    def apply_watermark(self, wav, sample_rate=None):
        return wav
perth.PerthImplicitWatermarker = NoopWatermarker

from chatterbox.tts import ChatterboxTTS
model = ChatterboxTTS.from_pretrained(device="mps")
model_name = "original"

text = {json.dumps(text)}
voice_sample = {json.dumps(voice_sample_path)}
exaggeration = {exaggeration}
cfg_weight = {cfg_weight}

start = time.time()
kwargs = dict(exaggeration=exaggeration, cfg_weight=cfg_weight)
if voice_sample:
    kwargs["audio_prompt_path"] = voice_sample
wav = model.generate(text, **kwargs)
elapsed = time.time() - start

output_path = {json.dumps(output_path)}
torchaudio.save(output_path, wav, model.sr)
duration = wav.shape[1] / model.sr

print(json.dumps({{"status": "ok", "model": model_name, "output_path": output_path, "duration": round(duration, 2), "generation_time": round(elapsed, 2)}}))
'''
    
    try:
        result = subprocess.run(
            [TTS_PYTHON, "-c", script],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=VIDKIT_DIR,
        )
        
        if result.returncode != 0:
            # Extract meaningful error
            stderr = result.stderr.strip().split("\n")
            error_line = stderr[-1] if stderr else "Unknown error"
            return {"status": "error", "message": error_line}
        
        # Find the JSON output line
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line.startswith("{"):
                return json.loads(line)
        
        return {"status": "error", "message": "No output from TTS process"}
    
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "TTS generation timed out (300s)"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def list_voice_samples() -> list[dict]:
    """List available voice samples."""
    samples = []
    for f in os.listdir(VOICE_SAMPLES_DIR):
        if f.endswith((".wav", ".mp3", ".m4a", ".flac")):
            path = os.path.join(VOICE_SAMPLES_DIR, f)
            name = os.path.splitext(f)[0]
            samples.append({"name": name, "path": path, "filename": f})
    return samples
