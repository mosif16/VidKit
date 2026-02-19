"""Auto-caption renderer — viral-style word-by-word animated subtitles.

Format based on Hormozi/CapCut viral caption standard:
- 1-2 words at a time, ALL CAPS
- Large bold font (~1/5 of screen width per word)
- Bottom-safe placement by default (~82-86% from top) to sit in letterbox/black-bar area when possible
- Rounded background pill behind text
- Active word highlighted in accent color
- Strong shadow/outline for readability on any background
"""
from __future__ import annotations
import os, subprocess, tempfile, math
from PIL import Image, ImageDraw, ImageFont
from backend.models import Project, TranscriptWord


# Style presets
STYLES = {
    "hormozi": {
        "fontsize_pct": 0.09,      # font size as % of frame height
        "words_per_group": 2,       # 1-2 words shown at a time
        "y_pct": 0.84,              # bottom-safe position (% from top)
        "text_color": (255, 255, 255),
        "highlight_color": (0, 255, 136),  # bright green highlight
        "bg_color": (0, 0, 0, 180),       # semi-transparent black pill
        "bg_padding": (20, 10),            # horizontal, vertical padding
        "bg_radius": 12,
        "outline_width": 0,
        "shadow": True,
        "uppercase": True,
    },
    "bold": {
        "fontsize_pct": 0.08,
        "words_per_group": 2,
        "y_pct": 0.84,
        "text_color": (255, 255, 255),
        "highlight_color": (255, 220, 0),  # yellow highlight
        "bg_color": (0, 0, 0, 200),
        "bg_padding": (24, 14),
        "bg_radius": 16,
        "outline_width": 0,
        "shadow": True,
        "uppercase": True,
    },
    "minimal": {
        "fontsize_pct": 0.055,
        "words_per_group": 3,
        "y_pct": 0.82,
        "text_color": (255, 255, 255),
        "highlight_color": (255, 255, 100),
        "bg_color": (0, 0, 0, 140),
        "bg_padding": (16, 8),
        "bg_radius": 8,
        "outline_width": 0,
        "shadow": False,
        "uppercase": False,
    },
    "default": {
        "fontsize_pct": 0.08,
        "words_per_group": 2,
        "y_pct": 0.84,
        "text_color": (255, 255, 255),
        "highlight_color": (255, 220, 0),
        "bg_color": (0, 0, 0, 180),
        "bg_padding": (22, 12),
        "bg_radius": 14,
        "outline_width": 0,
        "shadow": True,
        "uppercase": True,
    },
}


def render_caption_overlay(
    project: Project,
    output_path: str,
    width: int,
    height: int,
    fps: float = 30.0,
    style: str = "default",
) -> str:
    """Render transparent video overlay with viral-style captions."""
    s = STYLES.get(style, STYLES["default"])
    
    # Collect all words
    all_words = []
    for scene in project.scenes:
        for word in scene.transcript:
            if word.word.strip():
                all_words.append(word)
    
    if not all_words:
        return ""
    
    # Group into small display chunks (1-2 words)
    groups = _group_words(all_words, s["words_per_group"])
    
    # Calculate font size based on frame height
    fontsize = max(24, int(height * s["fontsize_pct"]))
    font = _get_bold_font(fontsize)
    
    # Total duration
    total_dur = sum((sc.end - sc.start) / sc.speed for sc in project.scenes)
    total_frames = int(total_dur * fps)
    
    # Pre-compute: for each group, which word is active at which time
    # Build a frame→group lookup for efficiency
    group_lookup = []
    for group in groups:
        start = group[0].start
        end = group[-1].end + 0.08  # tiny buffer
        group_lookup.append((start, end, group))
    
    # Render frames
    frames_dir = tempfile.mkdtemp(prefix="vidkit_cap_")
    
    for frame_idx in range(total_frames):
        t = frame_idx / fps
        
        # Find active group
        active_group = None
        for (start, end, group) in group_lookup:
            if start <= t <= end:
                active_group = group
                break
        
        img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        
        if active_group:
            _draw_caption_frame(img, active_group, t, font, s, width, height)
        
        frame_path = os.path.join(frames_dir, f"f_{frame_idx:06d}.png")
        img.save(frame_path, "PNG")
    
    # Encode to video with alpha
    subprocess.run([
        "ffmpeg", "-y",
        "-framerate", str(int(fps)),
        "-i", os.path.join(frames_dir, "f_%06d.png"),
        "-c:v", "qtrle",
        "-pix_fmt", "argb",
        output_path,
    ], capture_output=True, timeout=300)
    
    # Cleanup
    import shutil
    shutil.rmtree(frames_dir, ignore_errors=True)
    
    return output_path if os.path.exists(output_path) else ""


def _draw_caption_frame(
    img: Image.Image,
    group: list[TranscriptWord],
    t: float,
    font: ImageFont.FreeTypeFont,
    style: dict,
    width: int,
    height: int,
):
    """Draw a single caption frame with highlighted active word."""
    draw = ImageDraw.Draw(img)
    
    uppercase = style["uppercase"]
    margin_pct = 0.08  # 8% margin on each side
    max_text_w = int(width * (1.0 - 2 * margin_pct))
    
    # Build display text
    words_text = []
    for w in group:
        txt = w.word.strip()
        if uppercase:
            txt = txt.upper()
        words_text.append(txt)
    
    full_text = " ".join(words_text)
    
    # Auto-shrink font if text exceeds available width
    active_font = font
    bbox = draw.textbbox((0, 0), full_text, font=active_font)
    text_w = bbox[2] - bbox[0]
    
    if text_w > max_text_w:
        # Shrink font proportionally
        scale = max_text_w / text_w
        new_size = max(16, int(active_font.size * scale))
        active_font = _get_bold_font(new_size)
        bbox = draw.textbbox((0, 0), full_text, font=active_font)
        text_w = bbox[2] - bbox[0]
    
    text_h = bbox[3] - bbox[1]
    
    # Clamp: ensure text fits within frame
    text_w = min(text_w, max_text_w)
    
    # Position: centered horizontally, at y_pct vertically
    x = (width - text_w) // 2
    y = int(height * style["y_pct"]) - text_h // 2
    
    # Clamp position to stay on-screen
    pad_x, pad_y = style["bg_padding"]
    x = max(pad_x, min(x, width - text_w - pad_x))
    y = max(pad_y, min(y, height - text_h - pad_y))
    
    # Draw background pill
    bg_left = x - pad_x
    bg_top = y - pad_y
    bg_right = x + text_w + pad_x
    bg_bottom = y + text_h + pad_y
    radius = style["bg_radius"]
    
    bg_color = style["bg_color"]
    _draw_rounded_rect(draw, (bg_left, bg_top, bg_right, bg_bottom), radius, bg_color)
    
    # Draw shadow
    if style.get("shadow"):
        shadow_offset = max(2, int(text_h * 0.06))
        draw.text((x + shadow_offset, y + shadow_offset), full_text,
                  fill=(0, 0, 0, 160), font=active_font)
    
    # Draw each word — highlighted if active
    word_x = x
    for i, (word, txt) in enumerate(zip(group, words_text)):
        # Measure this word
        wbbox = draw.textbbox((0, 0), txt, font=active_font)
        ww = wbbox[2] - wbbox[0]
        
        # Is this word currently being spoken?
        is_active = word.start <= t <= word.end + 0.05
        
        if is_active:
            color = (*style["highlight_color"][:3], 255)
        else:
            color = (*style["text_color"][:3], 255)
        
        draw.text((word_x, y), txt, fill=color, font=active_font)
        
        # Add space width
        space_bbox = draw.textbbox((0, 0), " ", font=active_font)
        space_w = space_bbox[2] - space_bbox[0]
        word_x += ww + space_w


def _draw_rounded_rect(draw, coords, radius, color):
    """Draw a rounded rectangle."""
    x1, y1, x2, y2 = coords
    r = min(radius, (x2 - x1) // 2, (y2 - y1) // 2)
    
    # Main rectangle
    draw.rectangle([x1 + r, y1, x2 - r, y2], fill=color)
    draw.rectangle([x1, y1 + r, x2, y2 - r], fill=color)
    
    # Corners
    draw.pieslice([x1, y1, x1 + 2*r, y1 + 2*r], 180, 270, fill=color)
    draw.pieslice([x2 - 2*r, y1, x2, y1 + 2*r], 270, 360, fill=color)
    draw.pieslice([x1, y2 - 2*r, x1 + 2*r, y2], 90, 180, fill=color)
    draw.pieslice([x2 - 2*r, y2 - 2*r, x2, y2], 0, 90, fill=color)


def _group_words(words: list[TranscriptWord], max_per_group: int = 2) -> list[list[TranscriptWord]]:
    """Group words into small display chunks (1-2 words for viral style)."""
    groups = []
    current = []
    
    for word in words:
        current.append(word)
        text = word.word.strip()
        
        # Always break at max words
        if len(current) >= max_per_group:
            groups.append(current)
            current = []
        # Also break on sentence endings
        elif text.endswith(('.', '!', '?')):
            groups.append(current)
            current = []
    
    if current:
        groups.append(current)
    
    return groups


def _get_bold_font(size: int):
    """Get the boldest available font."""
    font_paths = [
        "/System/Library/Fonts/SFProDisplay-Heavy.otf",
        "/System/Library/Fonts/SFProDisplay-Black.otf",
        "/System/Library/Fonts/SFProDisplay-Bold.otf",
        "/Library/Fonts/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNS.ttf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def generate_srt_subtitles(project: Project, output_path: str) -> str:
    """Generate .srt subtitle file."""
    all_words = []
    for scene in project.scenes:
        for word in scene.transcript:
            if word.word.strip():
                all_words.append(word)
    
    groups = _group_words(all_words, max_per_group=3)
    
    srt = ""
    for i, group in enumerate(groups, 1):
        if not group:
            continue
        start = group[0].start
        end = group[-1].end
        text = " ".join(w.word.strip() for w in group)
        srt += f"{i}\n{_fmt_srt(start)} --> {_fmt_srt(end)}\n{text}\n\n"
    
    with open(output_path, "w") as f:
        f.write(srt)
    return output_path


def _fmt_srt(s: float) -> str:
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    ms = int((s % 1) * 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"
