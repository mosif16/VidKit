"""FFmpeg render engine — builds and executes ffmpeg commands from scene map."""
from __future__ import annotations
import subprocess, os, tempfile, math
from functools import lru_cache
from backend.models import Project, Scene, RenderPreset


def _probe_duration(path: str) -> float:
    """Best-effort media duration probe (seconds)."""
    try:
        result = subprocess.run([
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ], capture_output=True, text=True, timeout=20)
        return float((result.stdout or "0").strip() or 0)
    except Exception:
        return 0.0


def _build_atempo_chain(speed: float) -> list[str]:
    """Build chained atempo filters for speeds outside 0.5-2.0 range."""
    filters = []
    remaining = speed
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    if abs(remaining - 1.0) > 0.01:
        filters.append(f"atempo={remaining:.4f}")
    return filters


@lru_cache(maxsize=1)
def _drawtext_supported() -> bool:
    """Check if ffmpeg has drawtext support."""
    try:
        res = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True, timeout=10)
        out = (res.stdout or "") + (res.stderr or "")
        return "drawtext" in out
    except Exception:
        return False


def _build_text_filter(overlay, scene_duration: float) -> str:
    """Build ffmpeg drawtext filter for a text overlay."""
    pos_map = {
        "center": "(w-text_w)/2:(h-text_h)/2",
        "top": "(w-text_w)/2:h*0.08",
        "bottom": "(w-text_w)/2:h*0.88",
        "top-left": "w*0.05:h*0.08",
        "top-right": "w*0.95-text_w:h*0.08",
        "bottom-left": "w*0.05:h*0.88",
        "bottom-right": "w*0.95-text_w:h*0.88",
    }
    xy = pos_map.get(overlay.position, pos_map["center"])
    x, y = xy.split(":")

    dur = overlay.duration if overlay.duration > 0 else scene_duration
    enable = f"between(t,{overlay.start_offset},{overlay.start_offset + dur})"

    text = overlay.text.replace("'", "\\'").replace(":", "\\:")
    return (
        f"drawtext=text='{text}':fontsize={overlay.font_size}"
        f":fontcolor={overlay.color}:x={x}:y={y}"
        f":box=1:boxcolor={overlay.bg_color}:boxborderw=8"
        f":enable='{enable}'"
    )


def _extract_segment(scene: Scene, source_path: str, output_path: str, allow_text: bool = True) -> bool:
    """Extract and process a single scene segment."""
    has_speed = abs(scene.speed - 1.0) > 0.01

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(scene.start),
        "-t", str(scene.raw_duration),
        "-i", source_path,
    ]

    vfilters = []
    afilters = []

    # Speed
    if has_speed:
        vfilters.append(f"setpts={1/scene.speed}*PTS")
        afilters.extend(_build_atempo_chain(scene.speed))

    # Text overlays
    if allow_text:
        for overlay in scene.overlays:
            vfilters.append(_build_text_filter(overlay, scene.duration))

    # Fade in transition
    if scene.transition_in == "fade":
        d = scene.transition_duration
        vfilters.append(f"fade=t=in:st=0:d={d}")
        afilters.append(f"afade=t=in:st=0:d={d}")

    if vfilters:
        cmd += ["-vf", ",".join(vfilters)]
    if afilters:
        cmd += ["-af", ",".join(afilters)]

    cmd += [
        "-c:v", "h264_videotoolbox",
        "-q:v", "65",
        "-c:a", "aac", "-b:a", "192k",
    ]

    # When speed changes, setpts shortens video but ffmpeg may keep original duration.
    # Force output duration to match the effective (sped-up) duration.
    if has_speed:
        cmd += ["-t", str(scene.duration)]

    cmd.append(output_path)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        # Fallback to software encoder
        cmd_sw = []
        for c in cmd:
            if c == "h264_videotoolbox":
                cmd_sw.append("libx264")
            elif c == "65":
                cmd_sw.append("23")
            else:
                cmd_sw.append(c)
        result = subprocess.run(cmd_sw, capture_output=True, text=True, timeout=120)

    return result.returncode == 0


def render(
    project: Project,
    output_path: str,
    preset: RenderPreset | None = None,
    on_progress=None,
    burn_captions: bool = False,
    caption_style: str = "default",
) -> str:
    """Render the edited project to a video file."""
    if not project.scenes:
        raise ValueError("No scenes to render")

    temp_dir = tempfile.mkdtemp(prefix="vidkit_render_")

    try:
        segments_dir = os.path.join(temp_dir, "segments")
        os.makedirs(segments_dir, exist_ok=True)

        # Extract each scene as a segment
        segment_paths = []
        total = len(project.scenes)
        text_available = _drawtext_supported()
        if not text_available and any(scene.overlays for scene in project.scenes) and on_progress:
            on_progress("Warning: ffmpeg drawtext filter unavailable; rendering without text overlays.")

        for i, scene in enumerate(project.scenes):
            if on_progress:
                on_progress(f"Processing scene {i+1}/{total}...")

            seg_path = os.path.join(segments_dir, f"seg_{i:04d}.mp4")
            success = _extract_segment(scene, project.source_path, seg_path, allow_text=text_available)
            if success and os.path.exists(seg_path):
                segment_paths.append(seg_path)

        if not segment_paths:
            raise ValueError("No segments were rendered successfully")

        # Write concat file
        concat_path = os.path.join(temp_dir, "concat.txt")
        with open(concat_path, "w") as f:
            for path in segment_paths:
                f.write(f"file '{path}'\n")

        # Generate caption overlay if requested
        caption_overlay_path = ""
        if burn_captions:
            if on_progress:
                on_progress("Generating captions...")
            from backend.render.captions import render_caption_overlay
            target_w = preset.width if preset else (project.crop_width or project.width)
            target_h = preset.height if preset else (project.crop_height or project.height)
            caption_overlay_path = render_caption_overlay(
                project,
                os.path.join(temp_dir, "captions.mov"),
                width=target_w or project.width,
                height=target_h or project.height,
                fps=project.fps,
                style=caption_style,
            )

        if on_progress:
            on_progress("Concatenating final video...")

        # Build final output
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_path,
        ]

        vfilters = []

        # Apply preset (output resolution)
        target_w = preset.width if preset else (project.crop_width or project.width)
        target_h = preset.height if preset else (project.crop_height or project.height)

        if target_w and target_h:
            vfilters.append(
                f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
                f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black"
            )

        # Check for voiceover
        has_voiceover = bool(project.voiceover_path and os.path.exists(project.voiceover_path))

        if caption_overlay_path:
            # Two-pass: first concat without captions, then overlay
            temp_concat = os.path.join(temp_dir, "concat_nocap.mp4")
            
            concat_cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_path,
            ]
            if vfilters:
                concat_cmd += ["-vf", ",".join(vfilters)]
            concat_cmd += [
                "-c:v", "h264_videotoolbox", "-q:v", "65",
                "-c:a", "aac", "-b:a", "192k",
                temp_concat,
            ]
            result = subprocess.run(concat_cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                # Software fallback
                concat_cmd = [c if c != "h264_videotoolbox" else "libx264" for c in concat_cmd]
                concat_cmd = [c if c != "65" else "23" for c in concat_cmd]
                subprocess.run(concat_cmd, capture_output=True, text=True, timeout=600)
            
            # Overlay captions
            cmd = [
                "ffmpeg", "-y",
                "-i", temp_concat,
                "-i", caption_overlay_path,
                "-filter_complex", "[0:v][1:v]overlay=0:0:shortest=1[v]",
                "-map", "[v]", "-map", "0:a",
                "-c:v", "h264_videotoolbox", "-q:v", "65",
                "-c:a", "copy",
                "-movflags", "+faststart",
                output_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                cmd_sw = [c if c != "h264_videotoolbox" else "libx264" for c in cmd]
                cmd_sw = [c if c != "65" else "23" for c in cmd_sw]
                subprocess.run(cmd_sw, capture_output=True, text=True, timeout=600)
        else:
            # No captions — simple concat + encode
            if vfilters:
                cmd += ["-vf", ",".join(vfilters)]

            cmd += [
                "-c:v", "h264_videotoolbox",
                "-q:v", "65",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart",
                output_path,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                cmd_sw = []
                for c in cmd:
                    if c == "h264_videotoolbox":
                        cmd_sw.append("libx264")
                    elif c == "65":
                        cmd_sw.append("23")
                    else:
                        cmd_sw.append(c)
                subprocess.run(cmd_sw, capture_output=True, text=True, timeout=600)

        # Mix in voiceover if present
        if has_voiceover and os.path.exists(output_path):
            if on_progress:
                on_progress("Mixing voiceover...")

            vo_vol = project.voiceover_volume
            orig_vol = project.original_audio_volume
            temp_with_vo = os.path.join(temp_dir, "with_voiceover.mp4")

            video_duration = max(_probe_duration(output_path), 0.01)
            voice_duration = _probe_duration(project.voiceover_path)
            target_duration = video_duration

            # Keep narration natural: do not aggressively time-warp voice.
            # Policy:
            # - max voice speed-up: 1.08x
            # - max voice slow-down: 0.92x
            # - if mismatch is larger, extend video by freezing last frame
            #   so voice can remain natural.
            max_speedup = 1.08
            min_slowdown = 0.92

            input_video_path = output_path
            required_ratio = (voice_duration / video_duration) if video_duration > 0 else 1.0

            if required_ratio > max_speedup:
                # Voice is much longer than picture. Extend picture duration.
                extra = voice_duration - video_duration
                if extra > 0.03:
                    extended_path = os.path.join(temp_dir, "extended_for_voice.mp4")
                    extend_cmd = [
                        "ffmpeg", "-y",
                        "-i", output_path,
                        "-vf", f"tpad=stop_mode=clone:stop_duration={extra}",
                        "-af", "apad",
                        "-t", str(voice_duration),
                        "-c:v", "h264_videotoolbox", "-q:v", "65",
                        "-c:a", "aac", "-b:a", "192k",
                        extended_path,
                    ]
                    ext = subprocess.run(extend_cmd, capture_output=True, text=True, timeout=300)
                    if ext.returncode != 0:
                        extend_cmd_sw = [c if c != "h264_videotoolbox" else "libx264" for c in extend_cmd]
                        extend_cmd_sw = [c if c != "65" else "23" for c in extend_cmd_sw]
                        ext = subprocess.run(extend_cmd_sw, capture_output=True, text=True, timeout=300)
                    if ext.returncode == 0 and os.path.exists(extended_path):
                        input_video_path = extended_path
                        video_duration = max(_probe_duration(input_video_path), video_duration)

            target_duration = max(video_duration, 0.01)
            ratio_after_extension = (voice_duration / target_duration) if target_duration > 0 else 1.0

            voice_chain = [f"volume={vo_vol}"]
            # only apply gentle time adjustment in the natural-sounding range
            if ratio_after_extension > max_speedup:
                voice_chain.extend(_build_atempo_chain(max_speedup))
            elif ratio_after_extension < min_slowdown:
                voice_chain.extend(_build_atempo_chain(min_slowdown))
            elif abs(ratio_after_extension - 1.0) > 0.015:
                voice_chain.extend(_build_atempo_chain(ratio_after_extension))

            voice_chain.extend(["apad", f"atrim=0:{target_duration}"])
            voice_filter = ",".join(voice_chain)

            if orig_vol <= 0.001:
                filter_graph = f"[1:a]{voice_filter}[aout]"
            else:
                filter_graph = (
                    f"[0:a]volume={orig_vol},apad,atrim=0:{target_duration}[a0];"
                    f"[1:a]{voice_filter}[a1];"
                    f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[aout]"
                )

            vo_cmd = [
                "ffmpeg", "-y",
                "-i", input_video_path,
                "-i", project.voiceover_path,
                "-filter_complex", filter_graph,
                "-map", "0:v", "-map", "[aout]",
                "-t", str(target_duration),
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart",
                temp_with_vo,
            ]
            result = subprocess.run(vo_cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                # Replace output with voiceover version
                os.replace(temp_with_vo, output_path)

        if on_progress:
            on_progress("Done!")

        return output_path

    finally:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


def render_preview_frames(project: Project, output_dir: str, count: int = 10) -> list[str]:
    """Generate preview frames from the edited timeline."""
    os.makedirs(output_dir, exist_ok=True)
    total_duration = sum(s.duration for s in project.scenes)
    if total_duration == 0:
        return []
    interval = total_duration / max(count, 1)

    frames = []
    accumulated = 0
    frame_idx = 0

    for scene in project.scenes:
        scene_end = accumulated + scene.duration

        while frame_idx < count and frame_idx * interval < scene_end:
            target_time = frame_idx * interval
            # Map back to source time
            offset_in_scene = target_time - accumulated
            source_time = scene.start + (offset_in_scene * scene.speed)
            out_path = os.path.join(output_dir, f"preview_{frame_idx:03d}.jpg")

            subprocess.run([
                "ffmpeg", "-y", "-ss", str(source_time),
                "-i", project.source_path,
                "-frames:v", "1", "-q:v", "3", out_path
            ], capture_output=True, timeout=30)

            if os.path.exists(out_path):
                frames.append(out_path)
            frame_idx += 1

        accumulated = scene_end

    return frames
