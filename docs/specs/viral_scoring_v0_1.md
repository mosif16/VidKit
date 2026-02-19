# VidKit Viral Scoring & Planning Spec v0.1

## Purpose
Predict and improve short-form performance across Reels, TikTok, and Shorts with a two-stage score:
- Pre-publish quality score (PQS)
- Early performance score (EPS)

`VPS = 0.55 * PQS + 0.45 * EPS`

## Key Artifacts
- `backend/config/viral_scoring_weights.json`
- `backend/schemas/score_report.schema.json`
- `backend/schemas/edit_suggestions.schema.json`

## PQS Signals
Hook, time-to-value, pacing density, rewatch loop design, caption readability, audio fit, CTA quality, metadata relevance, originality, technical quality, safety.

## EPS Signals
Retention, completion, rewatch, share, save, comment quality, negative feedback (penalty), follower conversion, profile CTR, velocity.

## Pipeline Mapping
1. Brief intake
2. Ideation
3. Script/shotlist
4. Edit assembly
5. PQS gate
6. Publish + EPS checks (30/60/120m)
7. Learn/update weights

## Output Contracts
### `score_report`
- `pqs` / `eps` / `vps`
- `feature_contributions[]`
- `failed_gates[]`
- `recommendations[]`

### `edit_suggestions`
- ordered `suggestions[]` with `priority`, `action`, `timestamp_hint`
