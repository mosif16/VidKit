"""Main analysis pipeline — orchestrates scene detection, transcription, and vision."""
from __future__ import annotations
import subprocess, json, os, asyncio, uuid
from fractions import Fraction
from backend.models import Project, Scene, SceneType, TranscriptWord
from backend.core.scene_detect import detect_scenes, extract_thumbnails
from backend.core.transcriber import transcribe, get_words_for_range, detect_dead_air, detect_filler_words
from backend.core.vision import analyze_scenes


def get_video_info(video_path: str) -> dict:
    """Get video metadata via ffprobe."""
    result = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", video_path
    ], capture_output=True, text=True, timeout=30)
    data = json.loads(result.stdout)

    video_stream = next((s for s in data.get("streams", []) if s["codec_type"] == "video"), {})
    fps_raw = video_stream.get("r_frame_rate", "30/1")
    try:
        fps = float(Fraction(fps_raw))
    except Exception:
        fps = 30.0

    return {
        "duration": float(data.get("format", {}).get("duration", 0)),
        "width": int(video_stream.get("width", 0)),
        "height": int(video_stream.get("height", 0)),
        "fps": fps,
    }


async def analyze_video(
    video_path: str,
    project_dir: str,
    project_id: str | None = None,
    on_status=None,
    scene_threshold: float = 40.0,
    whisper_model: str = os.getenv("WHISPER_MODEL", "medium"),
) -> Project:
    """Full analysis pipeline. Returns a populated Project."""

    def status(msg: str):
        if on_status:
            on_status(msg)

    # 1. Video metadata
    status("Reading video metadata...")
    info = get_video_info(video_path)

    # Clean up project name from filename
    raw_name = os.path.splitext(os.path.basename(video_path))[0]
    # Strip UUID-like suffixes and common upload prefixes
    import re
    # Remove UUIDs, file prefixes, and clean up
    clean_name = re.sub(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', '', raw_name)
    clean_name = re.sub(r'^file_\d+---*', '', clean_name)
    clean_name = re.sub(r'[-_]+', ' ', clean_name).strip()
    if not clean_name or len(clean_name) < 3:
        # Fallback: use "Video" + timestamp
        from datetime import datetime
        clean_name = f"Video {datetime.now().strftime('%b %d %H:%M')}"

    project = Project(
        id=project_id or uuid.uuid4().hex[:8],
        name=clean_name,
        source_path=os.path.abspath(video_path),
        duration=info["duration"],
        width=info["width"],
        height=info["height"],
        fps=info["fps"],
        status="analyzing",
    )

    thumbs_dir = os.path.join(project_dir, project.id, "thumbnails")
    os.makedirs(thumbs_dir, exist_ok=True)

    # 2. Scene detection
    status("Detecting scenes...")
    raw_scenes = detect_scenes(video_path, threshold=scene_threshold)
    status(f"Found {len(raw_scenes)} scenes")

    # 2b. Merge short scenes if video is over-segmented
    if len(raw_scenes) > 1:
        merged = [raw_scenes[0]]
        for s in raw_scenes[1:]:
            prev = merged[-1]
            prev_dur = prev["end"] - prev["start"]
            cur_dur = s["end"] - s["start"]
            # Merge if either is under 1.5s
            if prev_dur < 1.5 or cur_dur < 1.5:
                prev["end"] = s["end"]
            else:
                merged.append(s)
        for i, s in enumerate(merged):
            s["id"] = f"s{i+1}"
        raw_scenes = merged
        status(f"Merged to {len(raw_scenes)} scenes")

    # 3. Extract thumbnails
    status("Extracting thumbnails...")
    thumb_paths = extract_thumbnails(video_path, raw_scenes, thumbs_dir)

    # 4. Transcription
    status("Transcribing audio (Whisper)...")
    transcript_data = transcribe(video_path, model=whisper_model)

    # 5. Detect dead air and filler words
    dead_air_gaps = detect_dead_air(transcript_data)
    filler_words = detect_filler_words(transcript_data)

    # 6. Vision analysis
    status("Analyzing scenes with vision model...")
    vision_results = await analyze_scenes(thumb_paths)

    # 7. Build scene objects
    status("Building scene map...")
    scenes = []
    for raw, vision in zip(raw_scenes, vision_results):
        words = get_words_for_range(transcript_data, raw["start"], raw["end"])
        is_dead = any(
            gap[0] >= raw["start"] and gap[1] <= raw["end"] and (gap[1] - gap[0]) > (raw["end"] - raw["start"]) * 0.7
            for gap in dead_air_gaps
        )

        scene = Scene(
            id=raw["id"],
            start=raw["start"],
            end=raw["end"],
            scene_type=vision.get("scene_type", SceneType.UNKNOWN),
            description=vision.get("description", ""),
            transcript=words,
            thumbnail_path=raw.get("thumbnail_path", ""),
            energy=vision.get("energy", 0.5),
            quality_score=vision.get("quality_score", 0.5),
            has_speech=bool(words) or vision.get("has_speech", False),
            is_dead_air=is_dead and not bool(words),
        )
        scenes.append(scene)

    project.scenes = scenes
    project.status = "ready"

    # Save project
    project_path = os.path.join(project_dir, project.id, "project.json")
    project.save(project_path)
    status(f"Analysis complete — {len(scenes)} scenes mapped")

    return project
