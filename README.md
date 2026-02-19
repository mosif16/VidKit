# VidKit

AI-assisted local video editing system for short-form content.

## What it does

- Upload and analyze videos
- Detect scenes and content opportunities
- Apply timeline edits (trim/speed/overlays)
- Generate voiceover and captions
- Render platform-ready outputs (Reels/TikTok/Shorts)

## Stack

- Backend: FastAPI (Python)
- Editing/Render: ffmpeg + custom pipeline
- Vision/analysis: local model integrations (Ollama-compatible)
- Voiceover: local TTS/voice-clone pipeline

## Project Structure

```txt
backend/
  api/        # REST endpoints
  core/       # analyzers, transcription, voice, creative logic
  render/     # ffmpeg render + audio mix
  models/     # project/scene/edit models
frontend/     # web UI shell
projects/     # runtime outputs (gitignored)
voice_samples/# local voice refs (gitignored)
```

## Quickstart

### 1) Create env + install deps

```bash
cd VidKit
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Run API

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8899
```

### 3) Health check

```bash
curl http://127.0.0.1:8899/api/health
```

## Minimal API flow

1. `POST /api/upload`
2. Poll `GET /api/project/{id}` until ready
3. `GET /api/project/{id}/analyze?platform=reels`
4. `POST /api/project/{id}/auto-edit`
5. `POST /api/project/{id}/voiceover`
6. `POST /api/project/{id}/render`

## Agent Reel Engine API (M1 dry-run)

New endpoint:

- `POST /api/agent/reel`

Purpose:
- Generate an autonomous reel plan from source + template + objective
- Return structured dry-run execution report (no real render yet)

Example request:

```json
{
  "source_video": "sample.mp4",
  "template": "viral-hook-v1",
  "platform": "reels",
  "objective": "maximize watch-time and shares",
  "duration_target_sec": 20,
  "tone": "high-energy"
}
```

Response includes:
- `plan` (selected best hook/cuts/captions/cta)
- `candidates` (generated variants considered for ranking)
- `score` (heuristic virality score for selected plan)
- `execution` (pipeline stage statuses + TODO steps)

See `docs/AGENT_REEL_ENGINE_PLAN.md` for milestone roadmap (M1–M4).

## Engineering Rules

See [AGENTS.md](./AGENTS.md) for mandatory agent workflow, safety limits, validation requirements, and media privacy rules.

## Privacy & Content Safety

VidKit is local-first. Runtime media, generated content, voice samples, and secrets must never be committed.

---

If you’re contributing, read [CONTRIBUTING.md](./CONTRIBUTING.md) first.
