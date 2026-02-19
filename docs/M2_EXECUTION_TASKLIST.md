# M2 Execution Task List — Agent Reel Engine

## End Goal
Ship a genuinely useful agent-controlled viral reel pipeline that can take a source video + template and output high-quality commercial/reel edits with natural audio and creative shot structure.

## Workstreams

### A) Audio/Video Sync Quality (in progress)
- [x] Add natural-speed guardrails for voice (`0.92x` to `1.08x`)
- [x] Extend video with freeze-frame when voice is much longer (avoid chipmunk audio)
- [ ] Add quality gate to reject renders with heavy speed distortion
- [ ] Add regression tests for voice duration alignment behavior

### B) Agent Planning → Real Timeline (next)
- [ ] Upgrade planner to output shot-level beat plan (hook/problem/solution/cta)
- [ ] Map scene detector output to beat allocations
- [ ] Build candidate timeline generator (3-5 variants)

### C) Creativity & Ranking Loop
- [ ] Add multi-candidate scoring (hook, pacing, captions, CTA, novelty)
- [ ] Select winner + attach rationale in execution report
- [ ] Add fallback when confidence is low

### D) Caption/Overlay System
- [ ] Move from static overlays to timed phrase chunks
- [ ] Emphasis styles (keywords/numbers)
- [ ] Platform-safe zones and readability checks

### E) End-to-End API
- [ ] Add execute mode in `/api/agent/reel` (currently dry-run only)
- [ ] Produce artifact paths + metrics summary in response
- [ ] Add smoke test covering plan → execute → render output

## Acceptance Criteria (M2)
- Audio is natural in final output (no obvious accelerated speech)
- Planner output drives actual edit decisions (not manual-only overlays)
- At least 3 candidates generated + ranked before final selection
- Successful output produced with clear report and score
