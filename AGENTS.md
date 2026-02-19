# AGENTS.md — VidKit Operating Guide

This file defines how agents should work in this repository.

## Mission

VidKit is an AI-assisted local video editing system. Priorities:
1. Reliability (no broken render/export paths)
2. A/V sync correctness (no narration drift/cutoff)
3. Creator outcomes (high-quality reels/shorts)
4. Safety/privacy (local-first handling of user media)

## Core Product Intent

Build an IDE-style editing workflow:
- ingest media
- analyze scenes/content
- suggest and apply edits
- generate voiceover/captions
- render predictable output

Agent work should improve one or more of: **speed, quality, determinism, UX clarity**.

---

## Safety & Autonomy Rules

### Autonomous by default
Agents should independently:
- inspect code
- implement fixes
- run tests/smoke scripts
- create branches, commit, push branches
- open PRs

### Hard limits
Never do these unless explicitly asked in the moment:
- delete projects/repositories/folders
- destructive commands (`rm -rf`, `git clean -fdx`, `git reset --hard`)
- commit/push directly to `main`/`master`
- force push
- delete remote branches/repos

### Mandatory git flow
Always use: **feature branch → commit → push branch → PR**.

### Main branch commitment (project policy)
VidKit’s canonical integration branch is `main`.

- All completed work should land in `main` via PR merge.
- Do not bypass review safety: no direct force-pushes to `main`.
- Keep branches short-lived and merge quickly so `main` stays the source of truth.

---

## Media & Privacy Rules

This repo must never commit private user content.

- Do not commit uploaded videos/audio/images
- Do not commit generated renders/previews/thumbnails
- Do not commit voice samples or cloned voice data
- Do not commit local credentials, tokens, or `.env` secrets

Use `.gitignore` and verify with `git status` before every commit.

---

## Architecture Map

- `backend/main.py` — FastAPI app bootstrap
- `backend/api/` — HTTP endpoints (upload/project/edit/analyze/render/voice)
- `backend/core/` — analysis, transcription, voice, creative logic
- `backend/render/ffmpeg.py` — render + audio mixing pipeline
- `backend/models/` — project/scene/edit models
- `frontend/` — UI shell
- `projects/` — runtime project outputs (ignored from git)

---

## Quality Bar for Changes

Any change touching render/audio must satisfy:

1. **No regression in export success**
2. **A/V timeline agreement** (video and muxed duration behavior intentional)
3. **Clear fallback behavior** if model/tool unavailable
4. **Actionable errors** from API (no silent failure)

When possible, include before/after verification notes.

---

## Standard Validation Steps

### Backend smoke
- start API
- upload sample clip
- poll project readiness
- run analyze
- run auto-edit (preview + apply)
- run voiceover
- run render
- verify output file exists + probe durations

### Suggested commands
- `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8899`
- `curl http://127.0.0.1:8899/api/health`
- `ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 <file>`

### Test reporting format
Include in PR/summary:
- what changed
- test commands
- pass/fail result
- known caveats

---

## Editing Principles

- Prefer small, reversible commits
- Keep API contracts stable unless required
- Preserve backward compatibility for project files where possible
- Avoid unsafe parsing (`eval`, unchecked shell interpolation)
- Use explicit time/duration handling for sync-critical code

---

## AI Integration Principles

For “brain” features (video/text/audio):
- deterministic defaults first
- model output must be validated before apply
- keep user-visible edits explainable
- never assume a model is available; fail gracefully with clear next steps

---

## PR Checklist

Before opening PR:
- [ ] `git status` clean except intended files
- [ ] no media/voice/content files staged
- [ ] smoke flow completed
- [ ] output behavior verified
- [ ] notes added (risk, fallback, follow-ups)

---

## Ownership Notes for Future Agents

When finishing a task, leave a concise handoff:
- current problem solved
- what remains
- exact repro/test command
- where to continue
