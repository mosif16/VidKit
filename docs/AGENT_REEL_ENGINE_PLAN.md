# Agent Reel Engine Plan (M1–M4)

## Intent
Build a unique, agent-controlled system that turns a source video + template/brief into high-quality viral-style reels using coordinated video/text/audio decisions.

## Architecture

### Inputs
- source video reference
- platform (reels/tiktok/shorts)
- objective (watch-time, shares, saves)
- template/style and tone

### Core Components
1. **Planner**: Converts brief into a structured ReelPlan (hook, cuts, captions, CTA)
2. **Scorer**: Estimates virality readiness from heuristic/model signals
3. **Orchestrator**: Runs pipeline stages and returns execution report
4. **Executor (future)**: Applies edit decisions to timeline and triggers render

### Data Contracts (M1)
- `AgentReelRequest`
- `ReelPlan`
- `PlanScore`
- `ExecutionReport` with stage-by-stage status
- `AgentReelResponse`

## Milestones

### M1 (this slice) — Dry-run foundation
- Define contracts and planning/scoring/orchestration modules
- Add `/api/agent/reel` endpoint (dry-run only)
- Return structured plan + score + report

### M2 — Timeline intelligence
- Integrate scene detector output into cut strategy
- Candidate cut generation and pruning
- Platform-specific pacing constraints

### M3 — Multimodal optimization loop
- Joint scoring for visual momentum + transcript hooks + audio cadence
- Multi-candidate A/B scoring and winner selection
- Confidence + fallback paths

### M4 — Production execution loop
- Execute winning plan through edit/render pipeline
- Captions/voiceover integration with strict A/V sync policy
- Agent-readable traces for iterative refinement

## Scoring Loop (target design)
1. Generate N candidate plans
2. Score each on hook strength, pacing, caption legibility, CTA clarity, novelty
3. Reject low-confidence candidates
4. Select best candidate and emit rationale
5. (Future) feed output metrics back into strategy priors

## Acceptance Criteria
- API returns deterministic structured response for valid requests
- Dry-run response includes plan, score, and pipeline stages
- Tests cover planner/scorer/orchestrator + endpoint shape
- No rendering side effects in M1

## Risks / TODOs
- Heuristic scorer may overfit generic hooks
- Need platform-specific empirical priors
- Must connect with real scene/audio/text signals in M2/M3
