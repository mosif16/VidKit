"""Vision model integration via Ollama for scene analysis."""
from __future__ import annotations
import base64, json, httpx, os
from backend.models import SceneType

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
VISION_MODEL = os.getenv("VISION_MODEL", "qwen2.5vl:latest")
VISION_FALLBACK_MODELS = [
    m.strip() for m in os.getenv("VISION_FALLBACK_MODELS", "qwen2.5vl:7b,minicpm-v:latest").split(",") if m.strip()
]

SCENE_ANALYSIS_PROMPT = """Analyze this video frame for short-form editing decisions.
Respond in STRICT JSON only (no markdown):
{
  "scene_type": "talking_head" | "screen_recording" | "broll" | "text_slide" | "dead_air" | "unknown",
  "description": "brief description of what is happening",
  "has_speech": true/false,
  "energy": 0.0-1.0,
  "quality_score": 0.0-1.0,
  "text_on_screen": "readable text or empty string",
  "hook_potential": 0.0-1.0,
  "visual_novelty": 0.0-1.0,
  "focus_subject": "main visible subject in a few words"
}"""


def _fallback_result(description: str = "") -> dict:
    return {
        "scene_type": SceneType.UNKNOWN,
        "description": description[:200],
        "has_speech": False,
        "energy": 0.5,
        "quality_score": 0.5,
        "text_on_screen": "",
        "hook_potential": 0.5,
        "visual_novelty": 0.5,
        "focus_subject": "",
    }


async def analyze_frame(image_path: str) -> dict:
    """Send a single frame to Ollama vision model with fallback retries."""
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    model_chain = [VISION_MODEL] + [m for m in VISION_FALLBACK_MODELS if m != VISION_MODEL]

    async with httpx.AsyncClient(timeout=120) as client:
        for model in model_chain:
            try:
                resp = await client.post(f"{OLLAMA_URL}/api/generate", json={
                    "model": model,
                    "prompt": SCENE_ANALYSIS_PROMPT,
                    "images": [img_b64],
                    "stream": False,
                    "options": {"temperature": 0.0},
                })
                resp.raise_for_status()
                data = resp.json()
                raw = data.get("response", "{}")

                # Handle markdown-wrapped JSON
                if "```" in raw:
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]

                result = json.loads(raw)

                st = result.get("scene_type", "unknown")
                try:
                    result["scene_type"] = SceneType(st)
                except ValueError:
                    result["scene_type"] = SceneType.UNKNOWN

                result.setdefault("hook_potential", 0.5)
                result.setdefault("visual_novelty", 0.5)
                result.setdefault("focus_subject", "")
                result["vision_model"] = model
                return result
            except Exception:
                continue

    return _fallback_result("vision analysis failed across all configured models")


async def analyze_scenes(thumbnail_paths: list[str], on_progress=None) -> list[dict]:
    """Analyze multiple scene thumbnails. Returns list of analysis results."""
    results = []
    for i, path in enumerate(thumbnail_paths):
        if os.path.exists(path):
            result = await analyze_frame(path)
        else:
            result = {
                "scene_type": SceneType.UNKNOWN,
                "description": "thumbnail not found",
                "has_speech": False,
                "energy": 0.5,
                "quality_score": 0.5,
                "text_on_screen": "",
            }
        results.append(result)
        if on_progress:
            on_progress(i + 1, len(thumbnail_paths))
    return results
