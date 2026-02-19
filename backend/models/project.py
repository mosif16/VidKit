"""Data models for VidKit projects."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
import json, uuid, time, copy


class SceneType(str, Enum):
    TALKING_HEAD = "talking_head"
    SCREEN_RECORDING = "screen_recording"
    BROLL = "broll"
    TEXT_SLIDE = "text_slide"
    DEAD_AIR = "dead_air"
    UNKNOWN = "unknown"


class EditKind(str, Enum):
    DELETE = "delete"
    REORDER = "reorder"
    TRIM = "trim"
    SPEED = "speed"
    SPLIT = "split"
    MERGE = "merge"
    TEXT_OVERLAY = "text_overlay"
    TRANSITION = "transition"
    CROP = "crop"


@dataclass
class TranscriptWord:
    word: str
    start: float
    end: float
    confidence: float = 1.0
    is_filler: bool = False


@dataclass
class TextOverlay:
    text: str = ""
    position: str = "bottom"  # top, center, bottom, top-left, top-right, bottom-left, bottom-right
    start_offset: float = 0.0  # seconds from scene start
    duration: float = 0.0  # 0 = full scene
    font_size: int = 48
    color: str = "white"
    bg_color: str = "black@0.5"


@dataclass
class Scene:
    id: str
    start: float
    end: float
    scene_type: SceneType = SceneType.UNKNOWN
    description: str = ""
    transcript: list[TranscriptWord] = field(default_factory=list)
    thumbnail_path: str = ""
    energy: float = 0.5
    quality_score: float = 0.5
    has_speech: bool = False
    is_filler: bool = False
    is_dead_air: bool = False
    speed: float = 1.0
    overlays: list[TextOverlay] = field(default_factory=list)
    transition_in: str = ""  # "", "fade", "dissolve"
    transition_duration: float = 0.5

    @property
    def duration(self) -> float:
        return (self.end - self.start) / self.speed

    @property
    def raw_duration(self) -> float:
        """Duration of source footage (ignoring speed)."""
        return self.end - self.start

    @property
    def transcript_text(self) -> str:
        return " ".join(w.word for w in self.transcript)


@dataclass
class Edit:
    kind: EditKind
    target_scene_id: str = ""
    params: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class RenderPreset:
    name: str
    width: int
    height: int
    fps: int = 30
    codec: str = "h264_videotoolbox"

    @staticmethod
    def tiktok() -> RenderPreset:
        return RenderPreset("TikTok/Reels", 1080, 1920)

    @staticmethod
    def youtube() -> RenderPreset:
        return RenderPreset("YouTube", 1920, 1080)

    @staticmethod
    def square() -> RenderPreset:
        return RenderPreset("Square", 1080, 1080)

    @staticmethod
    def original(w: int, h: int, fps: int = 30) -> RenderPreset:
        return RenderPreset("Original", w, h, fps)


@dataclass
class Project:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    source_path: str = ""
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 30.0
    scenes: list[Scene] = field(default_factory=list)
    edits: list[Edit] = field(default_factory=list)
    snapshots: list[str] = field(default_factory=list)  # JSON snapshots for undo
    crop_width: int = 0  # 0 = use original
    crop_height: int = 0
    voiceover_path: str = ""  # path to generated voiceover WAV
    voiceover_text: str = ""  # text used for voiceover
    voiceover_voice: str = ""  # voice sample name used
    voiceover_volume: float = 1.0  # voiceover volume (0.0 - 2.0)
    original_audio_volume: float = 0.0  # muted by default when voiceover active  # original audio volume when voiceover active (0.0 - 1.0)
    status: str = "created"  # created | analyzing | ready | rendering | done | error
    error: str = ""
    created_at: float = field(default_factory=time.time)

    def snapshot(self) -> str:
        """Save current scene state as a JSON snapshot for undo."""
        snap = json.dumps([_scene_to_dict(s) for s in self.scenes], default=str)
        self.snapshots.append(snap)
        # Keep max 50 snapshots
        if len(self.snapshots) > 50:
            self.snapshots = self.snapshots[-50:]
        return snap

    def undo(self) -> bool:
        """Restore previous scene state."""
        if not self.snapshots:
            return False
        snap = self.snapshots.pop()
        self.scenes = _scenes_from_list(json.loads(snap))
        if self.edits:
            self.edits.pop()
        return True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "source_path": self.source_path,
            "duration": self.duration,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "scenes": [_scene_to_dict(s) for s in self.scenes],
            "edits": [_edit_to_dict(e) for e in self.edits],
            "snapshots": self.snapshots,
            "crop_width": self.crop_width,
            "crop_height": self.crop_height,
            "voiceover_path": self.voiceover_path,
            "voiceover_text": self.voiceover_text,
            "voiceover_voice": self.voiceover_voice,
            "voiceover_volume": self.voiceover_volume,
            "original_audio_volume": self.original_audio_volume,
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)

    def save(self, path: str):
        with open(path, "w") as f:
            f.write(self.to_json())

    @staticmethod
    def load(path: str) -> Project:
        with open(path) as f:
            data = json.load(f)
        scenes = _scenes_from_list(data.pop("scenes", []))
        edits = []
        for e in data.pop("edits", []):
            edits.append(Edit(kind=EditKind(e["kind"]), target_scene_id=e.get("target_scene_id", ""),
                              params=e.get("params", {}), timestamp=e.get("timestamp", 0)))
        data.pop("snapshots", None)  # Don't restore snapshots from disk (they're large)
        return Project(**data, scenes=scenes, edits=edits)


def _scene_to_dict(s: Scene) -> dict:
    return {
        "id": s.id, "start": s.start, "end": s.end,
        "scene_type": s.scene_type.value,
        "description": s.description,
        "transcript": [{"word": w.word, "start": w.start, "end": w.end,
                        "confidence": w.confidence, "is_filler": w.is_filler} for w in s.transcript],
        "thumbnail_path": s.thumbnail_path,
        "energy": s.energy, "quality_score": s.quality_score,
        "has_speech": s.has_speech, "is_filler": s.is_filler, "is_dead_air": s.is_dead_air,
        "speed": s.speed,
        "overlays": [{"text": o.text, "position": o.position, "start_offset": o.start_offset,
                      "duration": o.duration, "font_size": o.font_size, "color": o.color,
                      "bg_color": o.bg_color} for o in s.overlays],
        "transition_in": s.transition_in,
        "transition_duration": s.transition_duration,
    }


def _edit_to_dict(e: Edit) -> dict:
    return {"kind": e.kind.value, "target_scene_id": e.target_scene_id,
            "params": e.params, "timestamp": e.timestamp}


def _scenes_from_list(scene_dicts: list[dict]) -> list[Scene]:
    scenes = []
    for s in scene_dicts:
        words = [TranscriptWord(word=w["word"], start=w["start"], end=w["end"],
                                confidence=w.get("confidence", 1.0),
                                is_filler=w.get("is_filler", False))
                 for w in s.get("transcript", [])]
        overlays = [TextOverlay(**o) for o in s.get("overlays", [])]
        scenes.append(Scene(
            id=s["id"], start=s["start"], end=s["end"],
            scene_type=SceneType(s.get("scene_type", "unknown")),
            description=s.get("description", ""),
            transcript=words, thumbnail_path=s.get("thumbnail_path", ""),
            energy=s.get("energy", 0.5), quality_score=s.get("quality_score", 0.5),
            has_speech=s.get("has_speech", False), is_filler=s.get("is_filler", False),
            is_dead_air=s.get("is_dead_air", False), speed=s.get("speed", 1.0),
            overlays=overlays, transition_in=s.get("transition_in", ""),
            transition_duration=s.get("transition_duration", 0.5),
        ))
    return scenes
