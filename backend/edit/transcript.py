"""Transcript-based editing — edit video by editing text."""
from __future__ import annotations
from backend.models import Project, Edit, EditKind, TranscriptWord
from backend.edit.engine import apply_edit


def delete_text_range(project: Project, start_time: float, end_time: float) -> Project:
    """Delete video content between two timestamps (from transcript selection)."""
    affected_scenes = [
        s for s in project.scenes
        if s.start < end_time and s.end > start_time
    ]

    for scene in affected_scenes:
        if scene.start >= start_time and scene.end <= end_time:
            # Entire scene is within deletion range
            project = apply_edit(project, Edit(
                kind=EditKind.DELETE,
                target_scene_id=scene.id,
            ))
        elif scene.start < start_time and scene.end > end_time:
            # Deletion is in the middle of scene — split twice
            # First split at start_time
            project = apply_edit(project, Edit(
                kind=EditKind.SPLIT,
                target_scene_id=scene.id,
                params={"split_at": start_time - scene.start},
            ))
            # Delete the middle part (which is now scene.id + "b")
            mid_id = f"{scene.id}b"
            # Split the middle part at end_time
            mid_scene = next((s for s in project.scenes if s.id == mid_id), None)
            if mid_scene:
                project = apply_edit(project, Edit(
                    kind=EditKind.SPLIT,
                    target_scene_id=mid_id,
                    params={"split_at": end_time - mid_scene.start},
                ))
                project = apply_edit(project, Edit(
                    kind=EditKind.DELETE,
                    target_scene_id=mid_id,
                ))
        elif scene.start < start_time:
            # Trim end of scene
            project = apply_edit(project, Edit(
                kind=EditKind.TRIM,
                target_scene_id=scene.id,
                params={"trim_end": scene.end - start_time},
            ))
        elif scene.end > end_time:
            # Trim start of scene
            project = apply_edit(project, Edit(
                kind=EditKind.TRIM,
                target_scene_id=scene.id,
                params={"trim_start": end_time - scene.start},
            ))

    return project


def delete_word(project: Project, word: TranscriptWord) -> Project:
    """Delete a single word from the video (with small buffer)."""
    buffer = 0.05  # 50ms buffer around word
    return delete_text_range(project, word.start - buffer, word.end + buffer)


def delete_all_filler_words(project: Project) -> Project:
    """Remove all detected filler words from the video."""
    from backend.core.transcriber import FILLER_WORDS

    # Collect all filler words across all scenes, sorted by time (reverse to avoid index shifting)
    fillers = []
    for scene in project.scenes:
        for word in scene.transcript:
            if word.word.lower().strip(".,!?") in FILLER_WORDS:
                fillers.append(word)

    fillers.sort(key=lambda w: w.start, reverse=True)

    for word in fillers:
        project = delete_word(project, word)

    # Remove ghost scenes (0 or negative duration)
    project.scenes = [s for s in project.scenes if s.raw_duration > 0.05]

    return project
