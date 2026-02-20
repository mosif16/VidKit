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

## AI brain + vision defaults

VidKit now defaults to stronger local AI settings:
- Vision: `qwen3-vl:latest` (Ollama)
- Vision fallbacks: `qwen3-vl:8b,qwen2.5vl:latest,qwen2.5vl:7b,minicpm-v:latest`
- Whisper transcription default: `medium`

Override via env vars:
- `VISION_MODEL`
- `VISION_FALLBACK_MODELS`
- `WHISPER_MODEL`

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

## Viral scoring config + contracts (v0.1)

VidKit now includes implementation-ready scoring artifacts:

- Config: `backend/config/viral_scoring_weights.json`
- Schemas:
  - `backend/schemas/score_report.schema.json`
  - `backend/schemas/edit_suggestions.schema.json`
- Spec: `docs/specs/viral_scoring_v0_1.md`

`POST /api/agent/reel` now returns two additional payloads for pipeline compatibility:
- `score_report` (PQS/EPS/VPS + contributions + recommendations)
- `edit_suggestions` (ordered timestamp-level action hints)

If scoring config is missing or malformed, backend falls back to safe defaults.

## Local Video Generation (CogVideoX-2B baseline)

Install generation deps:

```bash
pip install -r requirements.local-generation.txt
```

New endpoint:

- `POST /api/generate/local-video`

Example payload:

```json
{
  "prompt": "Cinematic short vertical video of sunrise over Manhattan skyline",
  "output_name": "cogvideox_local.mp4",
  "num_inference_steps": 12,
  "num_frames": 24,
  "width": 720,
  "height": 480,
  "fps": 8
}
```

Benchmark script:

```bash
python scripts/local_gen_benchmark.py
```

## Engineering Rules

See [AGENTS.md](./AGENTS.md) for mandatory agent workflow, safety limits, validation requirements, and media privacy rules.

## Privacy & Content Safety

VidKit is local-first. Runtime media, generated content, voice samples, and secrets must never be committed.

---

If you’re contributing, read [CONTRIBUTING.md](./CONTRIBUTING.md) first.
