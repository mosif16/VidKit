"""Chat-based editing — creative AI that actually watches the video."""
from __future__ import annotations
import json, httpx, os, re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.models import Edit, EditKind
from backend.edit.engine import apply_edit
from backend.api._state import projects, PROJECTS_DIR
from backend.core.creative_editor import analyze_for_editing, get_creative_suggestions

router = APIRouter()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-oss:20b-homer")

# Direct command patterns — user knows exactly what they want
DIRECT_PATTERNS = [
    r"delete\s+(?:scene\s+)?s\d+",
    r"speed\s+(?:up\s+)?(?:scene\s+)?s\d+",
    r"trim\s+(?:scene\s+)?s\d+",
    r"split\s+(?:scene\s+)?s\d+",
    r"merge\s+(?:scene\s+)?s\d+",
    r"reorder\s+(?:scene\s+)?s\d+",
    r"remove\s+(?:all\s+)?dead\s*air",
    r"remove\s+(?:all\s+)?filler",
    r"add\s+fade",
]

# Creative request patterns — user wants editorial judgment
CREATIVE_PATTERNS = [
    r"make\s+(?:it|this)\s+(?:more\s+)?(?:engaging|interesting|shorter|better|punchier|tighter)",
    r"what\s+should\s+I\s+(?:cut|remove|keep|change)",
    r"improve\s+(?:this|the\s+video|pacing|flow|hook)",
    r"(?:optimize|edit)\s+(?:for|as)\s+(?:reels|tiktok|shorts|youtube)",
    r"too\s+(?:long|slow|boring)",
    r"(?:tighten|punch)\s+(?:it|this)\s+up",
    r"(?:suggest|recommend)\s+(?:edits|changes|cuts)",
    r"what.+(?:boring|weak|redundant|repetitive)",
    r"(?:best|strongest|weakest)\s+(?:parts?|scenes?|moments?)",
    r"trim\s+(?:the\s+)?fat",
    r"make\s+(?:a|this)\s+(?:reel|tiktok|short)",
]

DIRECT_SYSTEM_PROMPT = """You are VidKit's edit assistant. Translate the user's request into a JSON array of edit commands.

Available edit commands:
- {"kind": "delete", "target_scene_id": "s1"}
- {"kind": "reorder", "target_scene_id": "s1", "params": {"new_index": 0}}
- {"kind": "trim", "target_scene_id": "s1", "params": {"trim_start": 2.0, "trim_end": 1.0}}
- {"kind": "speed", "target_scene_id": "s1", "params": {"speed": 1.5}}
- {"kind": "split", "target_scene_id": "s1", "params": {"split_at": 5.0}}
- {"kind": "merge", "target_scene_id": "s1"} — merges with next scene
- {"kind": "text_overlay", "target_scene_id": "s1", "params": {"text": "Hello", "position": "top", "font_size": 48, "duration": 3.0}}
- {"kind": "transition", "target_scene_id": "s1", "params": {"type": "fade", "duration": 0.5}}
- {"kind": "crop", "params": {"width": 1080, "height": 1920}}

Special string commands: "delete_dead_air", "delete_filler_words", "add_fade_transitions"

Respond with ONLY a JSON array. No explanation."""


class ChatRequest(BaseModel):
    message: str
    preview_only: bool = False


@router.post("/project/{project_id}/chat")
async def chat_edit(project_id: str, req: ChatRequest):
    proj = _get_project(project_id)
    msg_lower = req.message.lower().strip()

    # Detect mode: creative vs direct
    is_creative = any(re.search(p, msg_lower) for p in CREATIVE_PATTERNS)
    is_direct = any(re.search(p, msg_lower) for p in DIRECT_PATTERNS)

    # If both match or neither, use creative for longer/vague requests, direct for short/specific
    if is_creative and not is_direct:
        return await _creative_edit(proj, project_id, req)
    elif is_direct and not is_creative:
        return await _direct_edit(proj, project_id, req)
    elif is_creative:
        return await _creative_edit(proj, project_id, req)
    else:
        # Default: if the message mentions specific scene IDs, go direct; otherwise creative
        if re.search(r's\d+', msg_lower):
            return await _direct_edit(proj, project_id, req)
        return await _creative_edit(proj, project_id, req)


async def _creative_edit(proj, project_id: str, req: ChatRequest):
    """Creative mode: vision-analyze scenes, then make editorial decisions."""
    # Get deep editorial analysis (uses vision model on thumbnails)
    editorial = await analyze_for_editing(proj)

    # Get creative suggestions from LLM (returns tuple: advice string, parsed edits list)
    result = await get_creative_suggestions(proj, req.message, editorial)
    
    if isinstance(result, tuple):
        reasoning, commands = result
    elif isinstance(result, str):
        reasoning, commands = _parse_creative_response(result)
    else:
        reasoning, commands = "", []

    if req.preview_only:
        return {
            "status": "preview",
            "mode": "creative",
            "reasoning": reasoning,
            "proposed_edits": commands,
            "scene_count": len(proj.scenes),
            "editorial_analysis": {
                "narrative_arc": editorial["narrative_arc"],
                "scene_count": editorial["scene_count"],
                "total_duration": editorial["total_duration"],
            },
        }

    # Apply edits
    applied = _apply_commands(proj, commands)
    projects[project_id] = proj
    _save(proj)

    return {
        "status": "ok",
        "mode": "creative",
        "reasoning": reasoning,
        "applied": applied,
        "scene_count": len(proj.scenes),
    }


async def _direct_edit(proj, project_id: str, req: ChatRequest):
    """Direct mode: translate command to JSON edits (fast, no vision)."""
    scene_summary = []
    for s in proj.scenes:
        text = s.transcript_text[:80] if s.transcript_text else ""
        scene_summary.append(
            f"{s.id}: [{s.start:.1f}s-{s.end:.1f}s] {s.scene_type.value} "
            f"({s.duration:.1f}s) speed={s.speed}x "
            f"{'🗣' if s.has_speech else '🔇'} "
            f"{'⚠️dead_air' if s.is_dead_air else ''} "
            f"\"{text}\""
        )

    context = "Current scenes:\n" + "\n".join(scene_summary)
    user_msg = f"{context}\n\nUser request: {req.message}"

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{OLLAMA_URL}/api/generate", json={
            "model": CHAT_MODEL,
            "system": DIRECT_SYSTEM_PROMPT,
            "prompt": user_msg,
            "stream": False,
            "options": {"temperature": 0.1},
        })
        resp.raise_for_status()
        raw = resp.json().get("response", "[]")

    try:
        commands = _extract_json(raw)
    except (json.JSONDecodeError, ValueError):
        return {"status": "error", "message": "Could not parse AI response", "raw": raw}

    if req.preview_only:
        return {
            "status": "preview",
            "mode": "direct",
            "proposed_edits": commands,
            "scene_count": len(proj.scenes),
        }

    applied = _apply_commands(proj, commands)
    projects[project_id] = proj
    _save(proj)

    return {
        "status": "ok",
        "mode": "direct",
        "applied": applied,
        "scene_count": len(proj.scenes),
    }


def _parse_creative_response(raw: str) -> tuple[str, list]:
    """Parse the creative editor response into reasoning + commands."""
    reasoning = ""
    commands = []

    # Extract reasoning
    reasoning_match = re.search(r'REASONING:\s*(.+?)(?=EDITS:|```|$)', raw, re.DOTALL | re.IGNORECASE)
    if reasoning_match:
        reasoning = reasoning_match.group(1).strip()
    else:
        # Try to get everything before the JSON block
        json_start = raw.find("```")
        if json_start > 0:
            reasoning = raw[:json_start].strip()
        elif raw.find("[") > 0:
            reasoning = raw[:raw.find("[")].strip()

    # Extract JSON commands
    try:
        commands = _extract_json(raw)
    except (json.JSONDecodeError, ValueError):
        commands = []

    return reasoning, commands


def _extract_json(raw: str) -> list:
    """Extract JSON array from a response that may contain markdown/text."""
    # Try code block first
    if "```" in raw:
        blocks = re.findall(r'```(?:json)?\s*(.*?)```', raw, re.DOTALL)
        for block in blocks:
            try:
                result = json.loads(block.strip())
                if isinstance(result, list):
                    return result
                return [result]
            except json.JSONDecodeError:
                continue

    # Try to find a JSON array directly
    bracket_match = re.search(r'\[.*\]', raw, re.DOTALL)
    if bracket_match:
        try:
            result = json.loads(bracket_match.group())
            if isinstance(result, list):
                return result
            return [result]
        except json.JSONDecodeError:
            pass

    raise ValueError("No valid JSON found")


def _apply_commands(proj, commands: list) -> list:
    """Apply a list of edit commands to a project."""
    proj.snapshot()
    applied = []
    for cmd in commands:
        if isinstance(cmd, str):
            if cmd == "delete_dead_air":
                from backend.edit.engine import delete_dead_air
                proj_new = delete_dead_air(proj)
                proj.scenes = proj_new.scenes
                applied.append(cmd)
            elif cmd == "delete_filler_words":
                from backend.edit.transcript import delete_all_filler_words
                proj_new = delete_all_filler_words(proj)
                proj.scenes = proj_new.scenes
                applied.append(cmd)
            elif cmd == "add_fade_transitions":
                from backend.edit.engine import add_fade_transitions
                proj_new = add_fade_transitions(proj)
                proj.scenes = proj_new.scenes
                applied.append(cmd)
        elif isinstance(cmd, dict):
            try:
                edit = Edit(
                    kind=EditKind(cmd["kind"]),
                    target_scene_id=cmd.get("target_scene_id", ""),
                    params=cmd.get("params", {}),
                )
                proj_new = apply_edit(proj, edit)
                proj.scenes = proj_new.scenes
                applied.append(cmd)
            except (ValueError, KeyError) as e:
                applied.append({"error": str(e), "command": cmd})
    return applied


def _get_project(project_id: str):
    from backend.api.project import _get_project as gp
    return gp(project_id)


def _save(proj):
    path = os.path.join(PROJECTS_DIR, proj.id, "project.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    proj.save(path)
