"""Content-aware analysis for short-form video editing.

Implements research-backed best practices:
- 3-second hook detection
- Pacing analysis  
- Dead air compression
- Platform-specific length targeting
- Engagement scoring
"""
from __future__ import annotations
from dataclasses import dataclass
from backend.models import Project, Scene


# Platform ideal lengths (seconds) from research
PLATFORM_TARGETS = {
    "tiktok": {"min": 24, "max": 31, "ideal": 28},
    "reels": {"min": 7, "max": 15, "ideal": 12},
    "shorts": {"min": 15, "max": 60, "ideal": 30},
    "any": {"min": 7, "max": 60, "ideal": 20},
}


@dataclass
class HookAnalysis:
    has_speech_in_3s: bool
    first_word_time: float  # seconds until first word
    hook_text: str  # what's said in first 3s
    hook_score: float  # 0-1, how strong the hook is
    suggestion: str  # improvement suggestion


@dataclass
class PacingAnalysis:
    words_per_minute: float
    dead_air_seconds: float
    dead_air_pct: float
    longest_pause: float
    repetition_score: float  # 0-1, how much content repeats
    suggestion: str


@dataclass  
class EngagementScore:
    overall: float  # 0-100
    hook_score: float
    pacing_score: float
    caption_ready: bool
    length_score: float  # how well it fits platform targets
    breakdown: dict


def analyze_hook(project: Project) -> HookAnalysis:
    """Analyze the first 3 seconds for hook strength."""
    hook_words = []
    first_word_time = None
    
    for scene in project.scenes:
        for word in scene.transcript:
            if word.start <= 3.0:
                hook_words.append(word.word.strip())
                if first_word_time is None:
                    first_word_time = word.start
            if word.start > 3.0:
                break
    
    hook_text = " ".join(hook_words)
    has_speech = len(hook_words) > 0
    
    # Score the hook
    score = 0.0
    if has_speech:
        score += 0.3  # Speech exists in first 3s
        if first_word_time is not None and first_word_time < 0.5:
            score += 0.2  # Speech starts immediately
        if len(hook_words) >= 4:
            score += 0.2  # Enough words for a statement
        # Check for strong hook patterns
        hook_lower = hook_text.lower()
        strong_patterns = ["let me", "how to", "here's", "watch", "this is", "you need", 
                          "don't", "stop", "imagine", "what if", "the secret", "never"]
        if any(p in hook_lower for p in strong_patterns):
            score += 0.3  # Strong hook language
    
    suggestion = ""
    if not has_speech:
        suggestion = "⚠️ No speech in first 3s — viewers will swipe. Add a text hook or reorder scenes."
    elif first_word_time and first_word_time > 1.0:
        suggestion = "⚠️ Speech starts late — consider trimming the intro or adding text overlay."
    elif score < 0.5:
        suggestion = "Hook could be stronger. Consider starting with a question or bold statement."
    else:
        suggestion = "✅ Strong hook — speech starts fast with engaging content."
    
    return HookAnalysis(
        has_speech_in_3s=has_speech,
        first_word_time=first_word_time or 0.0,
        hook_text=hook_text,
        hook_score=min(score, 1.0),
        suggestion=suggestion,
    )


def analyze_pacing(project: Project) -> PacingAnalysis:
    """Analyze video pacing — dead air, speech density, repetition."""
    total_duration = sum(s.raw_duration for s in project.scenes)
    if total_duration == 0:
        return PacingAnalysis(0, 0, 0, 0, 0, "No content to analyze")
    
    # Count words and find gaps
    all_words = []
    for scene in project.scenes:
        all_words.extend(scene.transcript)
    
    total_words = len(all_words)
    wpm = (total_words / total_duration) * 60 if total_duration > 0 else 0
    
    # Find dead air (gaps > 0.5s between words)
    dead_air = 0.0
    longest_pause = 0.0
    for i in range(len(all_words) - 1):
        gap = all_words[i + 1].start - all_words[i].end
        if gap > 0.5:
            dead_air += gap
            longest_pause = max(longest_pause, gap)
    
    # Also count silence at start and end
    if all_words:
        dead_air += all_words[0].start  # silence before first word
        last_scene_end = project.scenes[-1].end if project.scenes else 0
        dead_air += last_scene_end - all_words[-1].end  # silence after last word
    
    dead_air_pct = dead_air / total_duration if total_duration > 0 else 0
    
    # Repetition detection — find repeated phrases
    word_texts = [w.word.strip().lower() for w in all_words]
    bigrams = [f"{word_texts[i]} {word_texts[i+1]}" for i in range(len(word_texts) - 1)]
    unique_bigrams = len(set(bigrams))
    repetition = 1.0 - (unique_bigrams / max(len(bigrams), 1))
    
    suggestion = ""
    if dead_air_pct > 0.3:
        suggestion = f"⚠️ {dead_air_pct*100:.0f}% dead air — use 'Remove Dead Air' to tighten."
    elif wpm < 100:
        suggestion = "⚠️ Low speech density — consider speeding up or cutting silent scenes."
    elif repetition > 0.4:
        suggestion = "⚠️ High repetition detected — consider cutting repeated phrases."
    else:
        suggestion = f"✅ Good pacing — {wpm:.0f} WPM, {dead_air_pct*100:.0f}% dead air."
    
    return PacingAnalysis(
        words_per_minute=wpm,
        dead_air_seconds=dead_air,
        dead_air_pct=dead_air_pct,
        longest_pause=longest_pause,
        repetition_score=repetition,
        suggestion=suggestion,
    )


def score_engagement(project: Project, target_platform: str = "any") -> EngagementScore:
    """Score the video's likely engagement/retention (0-100)."""
    hook = analyze_hook(project)
    pacing = analyze_pacing(project)
    
    total_duration = sum(s.duration for s in project.scenes)  # effective duration with speed
    target = PLATFORM_TARGETS.get(target_platform, PLATFORM_TARGETS["any"])
    
    # Hook score (0-30)
    hook_pts = hook.hook_score * 30
    
    # Pacing score (0-30)
    pacing_pts = 0
    if pacing.dead_air_pct < 0.1:
        pacing_pts += 15
    elif pacing.dead_air_pct < 0.2:
        pacing_pts += 10
    elif pacing.dead_air_pct < 0.3:
        pacing_pts += 5
    
    if pacing.words_per_minute > 120:
        pacing_pts += 15
    elif pacing.words_per_minute > 80:
        pacing_pts += 10
    elif pacing.words_per_minute > 50:
        pacing_pts += 5
    
    # Length score (0-20)
    length_pts = 0
    if target["min"] <= total_duration <= target["max"]:
        length_pts = 20
    elif total_duration < target["min"]:
        length_pts = max(0, 20 - (target["min"] - total_duration) * 3)
    else:
        length_pts = max(0, 20 - (total_duration - target["max"]) * 2)
    
    # Caption readiness (0-10)
    has_transcript = any(s.transcript for s in project.scenes)
    caption_pts = 10 if has_transcript else 0
    
    # Repetition penalty (0-10)
    rep_pts = max(0, 10 - pacing.repetition_score * 20)
    
    overall = hook_pts + pacing_pts + length_pts + caption_pts + rep_pts
    
    return EngagementScore(
        overall=min(overall, 100),
        hook_score=hook_pts,
        pacing_score=pacing_pts,
        caption_ready=has_transcript,
        length_score=length_pts,
        breakdown={
            "hook": f"{hook_pts:.0f}/30",
            "pacing": f"{pacing_pts:.0f}/30", 
            "length": f"{length_pts:.0f}/20 ({total_duration:.1f}s for {target_platform})",
            "captions": f"{caption_pts}/10",
            "repetition": f"{rep_pts:.0f}/10",
            "hook_detail": hook.suggestion,
            "pacing_detail": pacing.suggestion,
        },
    )


def auto_edit_for_platform(project: Project, platform: str = "reels") -> list[dict]:
    """Generate a list of suggested edits to optimize for a platform.
    
    Returns list of edit commands that can be applied via the edit engine.
    """
    target = PLATFORM_TARGETS.get(platform, PLATFORM_TARGETS["any"])
    total_duration = sum(s.duration for s in project.scenes)
    
    edits = []
    
    # 1. Remove dead air scenes
    for scene in project.scenes:
        if scene.is_dead_air:
            edits.append({
                "kind": "delete",
                "target_scene_id": scene.id,
                "reason": "Dead air — no value for viewer",
            })
    
    # 2. Trim trailing silence
    if project.scenes:
        last = project.scenes[-1]
        if last.transcript:
            last_word_end = last.transcript[-1].end
            trail = last.end - last_word_end
            if trail > 1.5:
                edits.append({
                    "kind": "trim",
                    "target_scene_id": last.id,
                    "params": {"trim_end": trail - 0.5},
                    "reason": f"Trim {trail:.1f}s trailing silence",
                })
        elif not last.has_speech and last.raw_duration > 2.0:
            edits.append({
                "kind": "trim",
                "target_scene_id": last.id,
                "params": {"trim_end": last.raw_duration - 1.0},
                "reason": "Trim silent ending scene",
            })
    
    # 3. Trim leading silence
    if project.scenes:
        first = project.scenes[0]
        if first.transcript:
            first_word = first.transcript[0].start - first.start
            if first_word > 0.8:
                edits.append({
                    "kind": "trim",
                    "target_scene_id": first.id,
                    "params": {"trim_start": first_word - 0.2},
                    "reason": f"Trim {first_word:.1f}s before first word",
                })
    
    # 4. If still too long for platform, find lowest-value scenes to cut
    remaining_dur = total_duration
    for e in edits:
        if e["kind"] == "delete":
            s = next((s for s in project.scenes if s.id == e["target_scene_id"]), None)
            if s:
                remaining_dur -= s.duration
        elif e["kind"] == "trim":
            remaining_dur -= e.get("params", {}).get("trim_end", 0)
            remaining_dur -= e.get("params", {}).get("trim_start", 0)
    
    if remaining_dur > target["max"]:
        # Need to cut more — find repetitive or low-energy scenes
        scored = []
        for scene in project.scenes:
            if scene.id in [e.get("target_scene_id") for e in edits if e["kind"] == "delete"]:
                continue
            # Score: lower = more cuttable
            score = 0
            if scene.has_speech:
                score += 2
            if scene.energy > 0.7:
                score += 1
            if scene.quality_score > 0.7:
                score += 1
            scored.append((score, scene))
        
        scored.sort(key=lambda x: x[0])
        
        for score, scene in scored:
            if remaining_dur <= target["ideal"]:
                break
            # Speed up low-value scenes rather than delete
            if score <= 2 and scene.duration > 2.0:
                speed = min(2.0, scene.duration / (scene.duration * 0.6))
                edits.append({
                    "kind": "speed",
                    "target_scene_id": scene.id,
                    "params": {"speed": round(speed, 2)},
                    "reason": f"Speed up low-value scene to fit {platform} length",
                })
                remaining_dur -= scene.duration * (1 - 1/speed)
    
    # 5. Add fade to last scene for clean ending
    if project.scenes:
        edits.append({
            "kind": "transition",
            "target_scene_id": project.scenes[-1].id,
            "params": {"type": "fade", "duration": 0.3},
            "reason": "Clean fade-out ending",
        })
    
    return edits
