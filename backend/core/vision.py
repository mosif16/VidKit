"""Vision model integration via Ollama for scene analysis."""
from __future__ import annotations
import base64, json, httpx, os
from backend.models import SceneType

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
VISION_MODEL = os.getenv("VISION_MODEL", "minicpm-v")

SCENE_ANALYSIS_PROMPT = """Analyze this video frame. Respond in JSON only, no other text:
{
  "scene_type": "talking_head" | "screen_recording" | "broll" | "text_slide" | "dead_air" | "unknown",
  "description": "brief description of what's happening",
  "has_speech": true/false (is someone talking or about to talk?),
  "energy": 0.0-1.0 (how visually dynamic/interesting is this frame?),
  "quality_score": 0.0-1.0 (image quality, lighting, focus),
  "text_on_screen": "any readable text, or empty string"
}"""


async def analyze_frame(image_path: str) -> dict:
    """Send a single frame to the vision model for analysis."""
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{OLLAMA_URL}/api/generate", json={
            "model": VISION_MODEL,
            "prompt": SCENE_ANALYSIS_PROMPT,
            "images": [img_b64],
            "stream": False,
            "options": {"temperature": 0.1},
        })
        resp.raise_for_status()
        data = resp.json()

    raw = data.get("response", "{}")
    # Try to parse JSON from response
    try:
        # Handle cases where model wraps JSON in markdown
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
    except (json.JSONDecodeError, IndexError):
        result = {
            "scene_type": "unknown",
            "description": raw[:200],
            "has_speech": False,
            "energy": 0.5,
            "quality_score": 0.5,
            "text_on_screen": "",
        }

    # Normalize scene_type
    st = result.get("scene_type", "unknown")
    try:
        result["scene_type"] = SceneType(st)
    except ValueError:
        result["scene_type"] = SceneType.UNKNOWN

    return result


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
