"""Audio transcription using Whisper."""
from __future__ import annotations
import subprocess, json, os, tempfile
from backend.models import TranscriptWord


def extract_audio(video_path: str, output_path: str | None = None) -> str:
    """Extract audio track from video as WAV."""
    if output_path is None:
        output_path = tempfile.mktemp(suffix=".wav")
    subprocess.run([
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        output_path
    ], capture_output=True, timeout=120)
    return output_path


def transcribe(video_path: str, model: str = "base", language: str = "en") -> dict:
    """Transcribe audio using Whisper CLI. Returns segments with word timestamps."""
    audio_path = extract_audio(video_path)
    
    output_dir = tempfile.mkdtemp()
    
    try:
        result = subprocess.run([
            "whisper", audio_path,
            "--model", model,
            "--language", language,
            "--output_format", "json",
            "--word_timestamps", "True",
            "--output_dir", output_dir,
        ], capture_output=True, text=True, timeout=600)

        # Find the JSON output
        json_files = [f for f in os.listdir(output_dir) if f.endswith(".json")]
        if not json_files:
            return {"segments": [], "words": []}

        with open(os.path.join(output_dir, json_files[0])) as f:
            data = json.load(f)

        return data
    finally:
        # Cleanup audio
        if os.path.exists(audio_path):
            os.remove(audio_path)


FILLER_WORDS = {"um", "uh", "erm", "uhm", "hmm", "you know", "basically", "literally", "i mean"}


def get_words_for_range(transcript_data: dict, start: float, end: float) -> list[TranscriptWord]:
    """Extract words that fall within a time range."""
    words = []
    for segment in transcript_data.get("segments", []):
        for w in segment.get("words", []):
            w_start = w.get("start", segment.get("start", 0))
            w_end = w.get("end", segment.get("end", 0))
            if w_start >= start and w_end <= end:
                text = w.get("word", "").strip()
                words.append(TranscriptWord(
                    word=text,
                    start=w_start,
                    end=w_end,
                    confidence=w.get("probability", 1.0),
                    is_filler=text.lower().strip(".,!?") in FILLER_WORDS,
                ))
    return words


def detect_dead_air(transcript_data: dict, min_gap: float = 2.0) -> list[tuple[float, float]]:
    """Find gaps in speech longer than min_gap seconds."""
    gaps = []
    all_words = []
    for seg in transcript_data.get("segments", []):
        for w in seg.get("words", []):
            all_words.append((w.get("start", seg["start"]), w.get("end", seg["end"])))
    
    all_words.sort(key=lambda x: x[0])
    for i in range(len(all_words) - 1):
        gap_start = all_words[i][1]
        gap_end = all_words[i + 1][0]
        if gap_end - gap_start >= min_gap:
            gaps.append((gap_start, gap_end))
    return gaps


def detect_filler_words(transcript_data: dict) -> list[TranscriptWord]:
    """Find filler words in transcript."""
    fillers = []
    for seg in transcript_data.get("segments", []):
        for w in seg.get("words", []):
            text = w.get("word", "").strip().lower().strip(".,!?")
            if text in FILLER_WORDS:
                fillers.append(TranscriptWord(
                    word=text,
                    start=w.get("start", seg["start"]),
                    end=w.get("end", seg["end"]),
                    confidence=w.get("probability", 1.0),
                ))
    return fillers
