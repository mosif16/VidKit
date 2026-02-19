"""Scene detection using PySceneDetect."""
from __future__ import annotations
import subprocess, json, os
from scenedetect import open_video, SceneManager, ContentDetector
from backend.models import Scene, SceneType


def detect_scenes(video_path: str, threshold: float = 40.0) -> list[dict]:
    """Detect scene boundaries using content-aware detection.
    
    Returns list of dicts with 'start' and 'end' timestamps in seconds.
    """
    video = open_video(video_path)
    sm = SceneManager()
    sm.add_detector(ContentDetector(threshold=threshold))
    sm.detect_scenes(video)
    scene_list = sm.get_scene_list()

    scenes = []
    for i, (start, end) in enumerate(scene_list):
        scenes.append({
            "id": f"s{i+1}",
            "start": start.get_seconds(),
            "end": end.get_seconds(),
        })

    # If no cuts detected, treat the whole video as one scene
    if not scenes:
        duration = video.duration.get_seconds()
        scenes.append({"id": "s1", "start": 0.0, "end": duration})

    # Merge very short scenes (<1s) into their neighbor
    merged = []
    for s in scenes:
        dur = s["end"] - s["start"]
        if dur < 1.0 and merged:
            merged[-1]["end"] = s["end"]
        else:
            merged.append(s)
    # Re-id after merge
    for i, s in enumerate(merged):
        s["id"] = f"s{i+1}"
    scenes = merged

    return scenes


def extract_thumbnails(video_path: str, scenes: list[dict], output_dir: str) -> list[str]:
    """Extract a thumbnail frame from the middle of each scene."""
    os.makedirs(output_dir, exist_ok=True)
    paths = []
    for scene in scenes:
        mid = (scene["start"] + scene["end"]) / 2
        out_path = os.path.join(output_dir, f"{scene['id']}.jpg")
        subprocess.run([
            "ffmpeg", "-y", "-ss", str(mid), "-i", video_path,
            "-frames:v", "1", "-q:v", "3", out_path
        ], capture_output=True, timeout=30)
        paths.append(out_path)
        scene["thumbnail_path"] = out_path
    return paths
