"""Creative AI editor — vision-powered editorial decision making.

This is the brain that actually WATCHES the video and makes creative
editing decisions, not just translates commands to JSON.
"""
from __future__ import annotations
import base64, json, os, httpx
from backend.models import Project, Scene

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
VISION_MODEL = os.getenv("VISION_MODEL", "minicpm-v")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-oss:20b-homer")


async def analyze_for_editing(project: Project) -> dict:
    """Deep editorial analysis: watch every scene and decide what's worth keeping.
    
    Returns a rich editorial breakdown the chat LLM can use to make decisions.
    """
    scene_analyses = []
    
    for scene in project.scenes:
        analysis = {
            "id": scene.id,
            "time": f"{scene.start:.1f}s-{scene.end:.1f}s",
            "duration": f"{scene.raw_duration:.1f}s",
            "transcript": scene.transcript_text or "(no speech)",
            "type": scene.scene_type.value,
            "energy": scene.energy,
            "quality": scene.quality_score,
            "description": scene.description,
            "text_on_screen": "",
            "has_speech": scene.has_speech,
            "is_dead_air": scene.is_dead_air,
        }
        
        # If we have a thumbnail, do a deeper editorial analysis with vision
        if scene.thumbnail_path and os.path.exists(scene.thumbnail_path):
            vision_analysis = await _editorial_vision_analysis(scene)
            # Ensure visual_content is always a string
            if isinstance(vision_analysis.get("visual_content"), dict):
                vc = vision_analysis["visual_content"]
                vision_analysis["visual_content"] = ", ".join(
                    f"{k}: {v}" for k, v in vc.items() if v
                ) if vc else scene.description
            analysis.update(vision_analysis)
        
        scene_analyses.append(analysis)
    
    # Build narrative arc analysis
    arc = _analyze_narrative_arc(project, scene_analyses)
    
    return {
        "scenes": scene_analyses,
        "narrative_arc": arc,
        "total_duration": sum(s.duration for s in project.scenes),
        "scene_count": len(project.scenes),
    }


async def get_creative_suggestions(project: Project, user_request: str, editorial_analysis: dict = None) -> str:
    """Ask the AI to make creative editing decisions based on actually seeing the video.
    
    Returns natural language editorial advice + JSON edit commands.
    """
    if editorial_analysis is None:
        editorial_analysis = await analyze_for_editing(project)
    
    # Build a rich context for the creative LLM
    scene_descriptions = []
    for sa in editorial_analysis["scenes"]:
        parts = [
            f"  Scene {sa['id']} [{sa['time']}] ({sa['duration']})",
            f"    Type: {sa['type']} | Energy: {sa['energy']:.1f} | Quality: {sa['quality']:.1f}",
            f"    Visual: {sa.get('visual_content', sa['description'])}",
        ]
        if sa.get("editorial_value"):
            parts.append(f"    Editorial value: {sa['editorial_value']}")
            if sa.get("editorial_reason"):
                parts.append(f"    Why: {sa['editorial_reason']}")
        if sa.get("emotion"):
            parts.append(f"    Emotion: {sa['emotion']}")
        if sa.get("text_on_screen"):
            parts.append(f"    On-screen text: {sa['text_on_screen']}")
        if sa["transcript"] != "(no speech)":
            parts.append(f"    Speech: \"{sa['transcript']}\"")
        if sa["is_dead_air"]:
            parts.append(f"    ⚠️ DEAD AIR — no visual or audio value")
        scene_descriptions.append("\n".join(parts))
    
    arc = editorial_analysis["narrative_arc"]
    
    context = f"""VIDEO BREAKDOWN ({editorial_analysis['total_duration']:.1f}s total, {editorial_analysis['scene_count']} scenes):

{chr(10).join(scene_descriptions)}

NARRATIVE ARC:
  Opening: {arc.get('opening', 'unknown')}
  Middle: {arc.get('middle', 'unknown')}
  Climax: {arc.get('climax', 'unknown')}
  Ending: {arc.get('ending', 'unknown')}
  Strongest moments: {', '.join(arc.get('strongest_scenes', []))}
  Weakest moments: {', '.join(arc.get('weakest_scenes', []))}
  Energy curve: {arc.get('energy_curve', 'flat')}"""

    prompt = f"""{context}

The user wants: {user_request}

You are a professional video editor. List your concrete edits FIRST, then explain why.

Use this exact format for each edit (one per line):
- Delete s2 — it's filler with no visual payoff
- Speed up s1 to 1.5x — the opening drags
- Trim 2s from the start of s3 — dead air before speech
- Move s3 to first — strongest hook
- Add fade on s5 — clean ending

Start with "EDITS:" then list each edit. After all edits, add "WHY:" with a brief explanation."""

    # Retry up to 2 times if LLM returns empty (Ollama sometimes does this)
    editorial_advice = ""
    for attempt in range(3):
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{OLLAMA_URL}/api/generate", json={
                "model": CHAT_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3 + attempt * 0.1, "num_predict": 2048},
            })
            resp.raise_for_status()
            editorial_advice = resp.json().get("response", "")
        if editorial_advice.strip():
            break
    
    if not editorial_advice.strip():
        return "", []
    
    # Second pass: convert natural language edits to JSON commands
    scene_ids = [s.id for s in project.scenes]
    json_edits = _parse_editorial_to_edits(editorial_advice, scene_ids)
    
    return editorial_advice, json_edits


def _parse_editorial_to_edits(advice: str, scene_ids: list[str]) -> list[dict]:
    """Parse natural language editorial advice into structured edit commands.
    
    Uses flexible regex patterns to extract suggestions from conversational LLM output.
    """
    import re
    edits = []
    clean = advice.lower()
    seen = set()  # avoid duplicate edits on same scene
    
    # Strip markdown bold/italic for matching
    clean = re.sub(r'\*+', '', clean)
    
    # --- DELETE patterns ---
    # "delete s4", "remove scene s2", "cut s1"
    for m in re.finditer(r'(?:delete|remove|cut|drop|lose)\s+(?:scene\s+)?(s\d+)', clean):
        sid = m.group(1)
        if sid in scene_ids and ('del', sid) not in seen:
            edits.append({"kind": "delete", "target_scene_id": sid})
            seen.add(('del', sid))
    # "sX ... delete/filler/redundant" (contextual, within same line/sentence)
    for m in re.finditer(r'(s\d+)\b[^.\n]{0,100}(?:filler|redundant|unnecessary|remove it|cut it|delete it|drop it|\bdelete\b)', clean):
        sid = m.group(1)
        if sid in scene_ids and ('del', sid) not in seen:
            edits.append({"kind": "delete", "target_scene_id": sid})
            seen.add(('del', sid))
    # "**Delete** entirely" after a scene mention — table format
    for m in re.finditer(r'(s\d+)[^|]{0,50}\|[^|]{0,100}(?:delete|remove|cut)\b', clean):
        sid = m.group(1)
        if sid in scene_ids and ('del', sid) not in seen:
            edits.append({"kind": "delete", "target_scene_id": sid})
            seen.add(('del', sid))
    
    # --- SPEED patterns ---
    # "speed up s1 to 1.5x", "s3 at 1.3x", "speed s2 1.5×"
    for m in re.finditer(r'(?:speed\s+(?:up\s+)?)?(?:scene\s+)?(s\d+)\s+(?:to\s+|at\s+)?(\d+\.?\d*)\s*[x×]', clean):
        sid, speed = m.group(1), float(m.group(2))
        if sid in scene_ids and 0.25 <= speed <= 4.0 and ('spd', sid) not in seen:
            edits.append({"kind": "speed", "target_scene_id": sid, "params": {"speed": speed}})
            seen.add(('spd', sid))
    # "1.5x on s1", "play s2 at 2x"
    for m in re.finditer(r'(\d+\.?\d*)\s*[x×]\s+(?:on|for|speed)?\s*(?:scene\s+)?(s\d+)', clean):
        speed, sid = float(m.group(1)), m.group(2)
        if sid in scene_ids and 0.25 <= speed <= 4.0 and ('spd', sid) not in seen:
            edits.append({"kind": "speed", "target_scene_id": sid, "params": {"speed": speed}})
            seen.add(('spd', sid))
    # Table: "s1 | ... | speed-up to 1.5x" 
    for m in re.finditer(r'(s\d+)[^|\n]{0,50}\|[^\n]{0,200}speed[^.\n]{0,30}(\d+\.?\d*)\s*[x×]', clean):
        sid, speed = m.group(1), float(m.group(2))
        if sid in scene_ids and 0.25 <= speed <= 4.0 and ('spd', sid) not in seen:
            edits.append({"kind": "speed", "target_scene_id": sid, "params": {"speed": speed}})
            seen.add(('spd', sid))
    # Broad: any sentence with sX and speed value
    for m in re.finditer(r'(s\d+)\b[^.\n]{0,80}(?:speed|ramp)[^.\n]{0,30}(\d+\.?\d*)\s*[x×]', clean):
        sid, speed = m.group(1), float(m.group(2))
        if sid in scene_ids and 0.25 <= speed <= 4.0 and ('spd', sid) not in seen:
            edits.append({"kind": "speed", "target_scene_id": sid, "params": {"speed": speed}})
            seen.add(('spd', sid))
    
    # --- TRIM patterns ---
    # "trim N seconds from start/end of sX" and many variations
    trim_patterns = [
        r'trim\s+(\d+\.?\d*)\s*(?:s(?:ec(?:onds?)?)?\s+)?(?:from\s+)?(?:the\s+)?(start|end|beginning|front|back)\s+(?:of\s+)?(?:scene\s+)?(s\d+)',
        r'trim\s+(?:scene\s+)?(s\d+)\s+(?:by\s+)?(\d+\.?\d*)\s*(?:s(?:ec(?:onds?)?)?\s+)?(?:from\s+)?(?:the\s+)?(start|end|beginning|front|back)',
        r'(?:shorten|cut)\s+(?:the\s+)?(start|end|beginning|front|back)\s+(?:of\s+)?(?:scene\s+)?(s\d+)\s+(?:by\s+)?(\d+\.?\d*)',
        r'(s\d+)\b[^.]{0,40}trim\s+(\d+\.?\d*)\s*s?\s+(?:from\s+)?(?:the\s+)?(start|end|beginning|front|back)',
    ]
    for pat in trim_patterns:
        for m in re.finditer(pat, clean):
            groups = m.groups()
            # Figure out which group is which
            sid = next(g for g in groups if g and re.match(r's\d+$', g))
            amount = next(float(g) for g in groups if g and re.match(r'\d+\.?\d*$', g))
            side = next(g for g in groups if g in ('start', 'end', 'beginning', 'front', 'back'))
            if sid in scene_ids and ('trm', sid) not in seen:
                is_start = side in ('start', 'beginning', 'front')
                params = {"trim_start": amount} if is_start else {"trim_end": amount}
                edits.append({"kind": "trim", "target_scene_id": sid, "params": params})
                seen.add(('trm', sid))
    
    # --- REORDER patterns ---
    for m in re.finditer(r'(?:reorder|move|put|place)\s+(?:scene\s+)?(s\d+)\s+(?:to\s+)?(?:be\s+)?(?:the\s+)?(first|last|beginning|end|opening|\d+)', clean):
        sid, pos = m.group(1), m.group(2)
        if sid in scene_ids and ('ord', sid) not in seen:
            idx = 0 if pos in ("first", "beginning", "opening") else (len(scene_ids) - 1 if pos in ("last", "end") else int(pos))
            edits.append({"kind": "reorder", "target_scene_id": sid, "params": {"new_index": idx}})
            seen.add(('ord', sid))
    # "use sX as the hook/opener"
    for m in re.finditer(r'(?:use\s+)?(?:scene\s+)?(s\d+)\s+(?:as\s+)?(?:the\s+)?(?:hook|opener|opening|first)', clean):
        sid = m.group(1)
        if sid in scene_ids and ('ord', sid) not in seen:
            edits.append({"kind": "reorder", "target_scene_id": sid, "params": {"new_index": 0}})
            seen.add(('ord', sid))
    # "move s3 to the very beginning" / table: "re-order | move s3 to..."
    for m in re.finditer(r'(?:move|re-?order)\s+(?:scene\s+)?(s\d+)\s+(?:to\s+)?(?:the\s+)?(?:very\s+)?(beginning|start|first|front)', clean):
        sid = m.group(1)
        if sid in scene_ids and ('ord', sid) not in seen:
            edits.append({"kind": "reorder", "target_scene_id": sid, "params": {"new_index": 0}})
            seen.add(('ord', sid))
    
    # Broad trim: "trim 0.5 s from the end of s4" or "trim 1 s from the start"
    for m in re.finditer(r'(?:trim|cut)\s+(?:the\s+)?(?:last\s+|first\s+)?(\d+\.?\d*)\s*s?\s+(?:from\s+)?(?:the\s+)?(?:end|start|beginning)\s+(?:of\s+)?(?:scene\s+)?(s\d+)', clean):
        amount, sid = float(m.group(1)), m.group(2)
        is_end = 'end' in m.group(0) or 'last' in m.group(0)
        if sid in scene_ids and ('trm', sid) not in seen:
            params = {"trim_end": amount} if is_end else {"trim_start": amount}
            edits.append({"kind": "trim", "target_scene_id": sid, "params": params})
            seen.add(('trm', sid))
    # "s1 ... trim 1 s from the start"
    for m in re.finditer(r'(s\d+)\b[^.\n]{0,100}trim\s+(\d+\.?\d*)\s*s?\s+(?:from\s+)?(?:the\s+)?(start|end|beginning|front|back)', clean):
        sid, amount, side = m.group(1), float(m.group(2)), m.group(3)
        if sid in scene_ids and ('trm', sid) not in seen:
            is_start = side in ('start', 'beginning', 'front')
            params = {"trim_start": amount} if is_start else {"trim_end": amount}
            edits.append({"kind": "trim", "target_scene_id": sid, "params": params})
            seen.add(('trm', sid))
    
    # Table trim: "s5 | ... | cut the last 0.5 s"
    for m in re.finditer(r'(s\d+)[^|]{0,50}\|[^|]{0,150}(?:cut|trim)\s+(?:the\s+)?(?:last|end(?:ing)?)\s+(\d+\.?\d*)', clean):
        sid, amount = m.group(1), float(m.group(2))
        if sid in scene_ids and ('trm', sid) not in seen:
            edits.append({"kind": "trim", "target_scene_id": sid, "params": {"trim_end": amount}})
            seen.add(('trm', sid))
    for m in re.finditer(r'(s\d+)[^|]{0,50}\|[^|]{0,150}(?:cut|trim)\s+(?:the\s+)?(?:first|start|beginning)\s+(\d+\.?\d*)', clean):
        sid, amount = m.group(1), float(m.group(2))
        if sid in scene_ids and ('trm', sid) not in seen:
            edits.append({"kind": "trim", "target_scene_id": sid, "params": {"trim_start": amount}})
            seen.add(('trm', sid))
    
    # --- TRANSITION patterns ---
    for m in re.finditer(r'(?:add\s+)?(?:a\s+)?fade\s+(?:transition\s+)?(?:on|to|for|at|into)?\s*(?:scene\s+)?(s\d+)', clean):
        sid = m.group(1)
        if sid in scene_ids and ('tr', sid) not in seen:
            edits.append({"kind": "transition", "target_scene_id": sid, "params": {"type": "fade", "duration": 0.3}})
            seen.add(('tr', sid))
    # "fade out on sX", "sX with a fade"
    for m in re.finditer(r'(s\d+)\b[^.]{0,30}(?:with\s+a\s+)?fade', clean):
        sid = m.group(1)
        if sid in scene_ids and ('tr', sid) not in seen:
            edits.append({"kind": "transition", "target_scene_id": sid, "params": {"type": "fade", "duration": 0.3}})
            seen.add(('tr', sid))
    
    # "fade to black" / "fade out" on last scene if mentioned
    if re.search(r'fade[\s-]*(?:to[\s-]*black|out)', clean) and scene_ids:
        last = scene_ids[-1]
        if ('tr', last) not in seen:
            edits.append({"kind": "transition", "target_scene_id": last, "params": {"type": "fade", "duration": 0.3}})
            seen.add(('tr', last))
    
    # --- MERGE ---
    for m in re.finditer(r'merge\s+(?:scene\s+)?(s\d+)', clean):
        sid = m.group(1)
        if sid in scene_ids and ('mrg', sid) not in seen:
            edits.append({"kind": "merge", "target_scene_id": sid})
            seen.add(('mrg', sid))
    
    # --- SPECIAL ---
    if re.search(r'(?:remove|delete|cut|clean)\s+(?:all\s+)?(?:the\s+)?dead\s*air', clean):
        edits.append("delete_dead_air")
    if re.search(r'(?:remove|delete|cut|clean)\s+(?:all\s+)?(?:the\s+)?filler\s*(?:words?)?', clean):
        edits.append("delete_filler_words")
    
    return edits


async def _editorial_vision_analysis(scene: Scene) -> dict:
    """Ask the vision model to evaluate a scene from an EDITING perspective."""
    if not scene.thumbnail_path or not os.path.exists(scene.thumbnail_path):
        return {}
    
    with open(scene.thumbnail_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    
    prompt = """You are a professional video editor reviewing this frame. Respond in JSON only:
{
  "visual_content": "what's actually shown (people, actions, objects, setting)",
  "text_on_screen": "any readable text or empty string",
  "editorial_value": "high" | "medium" | "low",
  "editorial_reason": "why this is/isn't worth keeping (1 sentence)",
  "emotion": "the emotional tone (energetic, calm, dramatic, boring, funny, intense, etc)",
  "is_redundant_with_neighbors": false
}"""
    
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{OLLAMA_URL}/api/generate", json={
                "model": VISION_MODEL,
                "prompt": prompt,
                "images": [img_b64],
                "stream": False,
                "options": {"temperature": 0.1},
            })
            resp.raise_for_status()
            raw = resp.json().get("response", "{}")
        
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception:
        return {}


def _analyze_narrative_arc(project: Project, scene_analyses: list[dict]) -> dict:
    """Analyze the story arc from scene data."""
    if not scene_analyses:
        return {"opening": "empty", "middle": "empty", "climax": "empty", "ending": "empty"}
    
    n = len(scene_analyses)
    
    # Find energy peaks
    energies = [(sa["energy"], sa["id"]) for sa in scene_analyses]
    sorted_by_energy = sorted(energies, key=lambda x: x[0], reverse=True)
    strongest = [sid for _, sid in sorted_by_energy[:max(1, n // 3)]]
    weakest = [sid for _, sid in sorted_by_energy[-max(1, n // 3):]]
    
    # Determine energy curve
    if n >= 3:
        first_third = sum(sa["energy"] for sa in scene_analyses[:n//3]) / max(1, n//3)
        mid_third = sum(sa["energy"] for sa in scene_analyses[n//3:2*n//3]) / max(1, n//3)
        last_third = sum(sa["energy"] for sa in scene_analyses[2*n//3:]) / max(1, n - 2*n//3)
        
        if last_third > first_third and last_third > mid_third:
            curve = "building (energy increases → strong ending)"
        elif first_third > mid_third and first_third > last_third:
            curve = "front-loaded (starts strong, fades)"
        elif mid_third > first_third and mid_third > last_third:
            curve = "peaks in middle"
        else:
            curve = "relatively flat"
    else:
        curve = "too short to analyze arc"
    
    # Summarize sections
    opening = scene_analyses[0]
    ending = scene_analyses[-1]
    
    return {
        "opening": f"{opening.get('visual_content', opening['description'])} ({opening['type']})",
        "middle": f"{n - 2} scenes" if n > 2 else "single scene",
        "climax": f"Scene {sorted_by_energy[0][1]} (energy {sorted_by_energy[0][0]:.1f})" if sorted_by_energy else "none",
        "ending": f"{ending.get('visual_content', ending['description'])} ({ending['type']})",
        "strongest_scenes": strongest,
        "weakest_scenes": weakest,
        "energy_curve": curve,
    }
