"""Edit engine — applies non-destructive edits to the scene map."""
from __future__ import annotations
from backend.models import Project, Scene, Edit, EditKind, TextOverlay


def apply_edit(project: Project, edit: Edit) -> Project:
    """Apply a single edit to a project. Snapshots state before each edit for undo."""
    project.snapshot()
    project.edits.append(edit)

    handlers = {
        EditKind.DELETE: _delete_scene,
        EditKind.REORDER: _reorder_scene,
        EditKind.TRIM: _trim_scene,
        EditKind.SPEED: _speed_scene,
        EditKind.SPLIT: _split_scene,
        EditKind.MERGE: _merge_scenes,
        EditKind.TEXT_OVERLAY: _text_overlay,
        EditKind.TRANSITION: _transition,
        EditKind.CROP: _crop,
    }
    handler = handlers.get(edit.kind)
    if handler:
        project = handler(project, edit)
    return project


def apply_edits(project: Project, edits: list[Edit]) -> Project:
    for edit in edits:
        project = apply_edit(project, edit)
    return project


def _delete_scene(project: Project, edit: Edit) -> Project:
    project.scenes = [s for s in project.scenes if s.id != edit.target_scene_id]
    return project


def _reorder_scene(project: Project, edit: Edit) -> Project:
    new_index = edit.params.get("new_index", 0)
    scene = next((s for s in project.scenes if s.id == edit.target_scene_id), None)
    if scene:
        project.scenes.remove(scene)
        project.scenes.insert(min(new_index, len(project.scenes)), scene)
    return project


def _trim_scene(project: Project, edit: Edit) -> Project:
    for scene in project.scenes:
        if scene.id == edit.target_scene_id:
            trim_start = edit.params.get("trim_start", 0)
            trim_end = edit.params.get("trim_end", 0)
            scene.start += trim_start
            scene.end -= trim_end
            scene.transcript = [
                w for w in scene.transcript
                if w.start >= scene.start and w.end <= scene.end
            ]
            break
    return project


def _speed_scene(project: Project, edit: Edit) -> Project:
    for scene in project.scenes:
        if scene.id == edit.target_scene_id:
            speed = edit.params.get("speed", 1.0)
            speed = max(0.25, min(4.0, speed))  # clamp to safe range
            scene.speed = speed
            break
    return project


def _split_scene(project: Project, edit: Edit) -> Project:
    split_at = edit.params.get("split_at", 0)
    for i, scene in enumerate(project.scenes):
        if scene.id == edit.target_scene_id:
            abs_split = scene.start + split_at
            if abs_split <= scene.start or abs_split >= scene.end:
                break

            scene2 = Scene(
                id=f"{scene.id}b",
                start=abs_split,
                end=scene.end,
                scene_type=scene.scene_type,
                description=scene.description,
                transcript=[w for w in scene.transcript if w.start >= abs_split],
                thumbnail_path=scene.thumbnail_path,
                energy=scene.energy,
                quality_score=scene.quality_score,
                has_speech=scene.has_speech,
                speed=scene.speed,
            )
            scene.end = abs_split
            scene.transcript = [w for w in scene.transcript if w.end <= abs_split]
            project.scenes.insert(i + 1, scene2)
            break
    return project


def _merge_scenes(project: Project, edit: Edit) -> Project:
    """Merge target scene with the next scene."""
    target_id = edit.target_scene_id
    for i, scene in enumerate(project.scenes):
        if scene.id == target_id and i + 1 < len(project.scenes):
            next_scene = project.scenes[i + 1]
            scene.end = next_scene.end
            scene.transcript.extend(next_scene.transcript)
            scene.has_speech = scene.has_speech or next_scene.has_speech
            scene.description = f"{scene.description}; {next_scene.description}".strip("; ")
            # Use higher energy/quality of the two
            scene.energy = max(scene.energy, next_scene.energy)
            scene.quality_score = min(scene.quality_score, next_scene.quality_score)
            project.scenes.pop(i + 1)
            break
    return project


def _text_overlay(project: Project, edit: Edit) -> Project:
    for scene in project.scenes:
        if scene.id == edit.target_scene_id:
            scene.overlays.append(TextOverlay(
                text=edit.params.get("text", ""),
                position=edit.params.get("position", "bottom"),
                start_offset=edit.params.get("start_offset", 0),
                duration=edit.params.get("duration", 0),
                font_size=edit.params.get("font_size", 48),
                color=edit.params.get("color", "white"),
                bg_color=edit.params.get("bg_color", "black@0.5"),
            ))
            break
    return project


def _transition(project: Project, edit: Edit) -> Project:
    """Add a transition effect to a scene."""
    for scene in project.scenes:
        if scene.id == edit.target_scene_id:
            scene.transition_in = edit.params.get("type", "fade")  # fade, dissolve
            scene.transition_duration = edit.params.get("duration", 0.5)
            break
    return project


def _crop(project: Project, edit: Edit) -> Project:
    project.crop_width = edit.params.get("width", project.width)
    project.crop_height = edit.params.get("height", project.height)
    return project


# Convenience functions
def delete_dead_air(project: Project) -> Project:
    dead = [s for s in project.scenes if s.is_dead_air]
    for scene in dead:
        project = apply_edit(project, Edit(kind=EditKind.DELETE, target_scene_id=scene.id))
    return project


def delete_filler_scenes(project: Project, min_duration: float = 0.5) -> Project:
    short = [s for s in project.scenes if s.duration < min_duration]
    for scene in short:
        project = apply_edit(project, Edit(kind=EditKind.DELETE, target_scene_id=scene.id))
    return project


def add_fade_transitions(project: Project, duration: float = 0.5) -> Project:
    """Add fade transitions between all scenes."""
    for scene in project.scenes[1:]:  # skip first scene
        project = apply_edit(project, Edit(
            kind=EditKind.TRANSITION,
            target_scene_id=scene.id,
            params={"type": "fade", "duration": duration},
        ))
    return project
