# Contributing to VidKit

Thanks for contributing.

## Workflow (required)

1. Create a feature branch
2. Implement focused changes
3. Run validation/smoke tests
4. Commit with clear message
5. Push branch and open PR

Never commit directly to `main`.

## Branch naming

Use one of:
- `fix/<topic>`
- `feat/<topic>`
- `chore/<topic>`
- `docs/<topic>`

## Commit style

Use conventional-ish prefixes:
- `fix:` bug fix
- `feat:` feature
- `docs:` documentation
- `chore:` maintenance
- `refactor:` code restructuring

## Validation expectations

For render/audio/voice changes, include:
- upload → analyze → edit → voiceover → render smoke flow
- output existence check
- duration check via `ffprobe`

Example:
```bash
ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 <output.mp4>
```

## PR template expectations

PR description should include:
- Summary of change
- Why change was needed
- Validation commands + result
- Risks/caveats

## Media & Secrets policy

Never commit:
- video/audio/image content
- generated renders/thumbnails
- voice samples/templates containing personal data
- API keys/tokens/private keys/.env secrets

Check staged files before commit:
```bash
git status
```

## Code quality guidelines

- Keep changes small and reversible
- Prefer explicit error handling over silent failures
- Keep API responses actionable
- Avoid unsafe evaluation/parsing patterns
- Preserve backward compatibility for project files where possible

## Documentation updates

If behavior changes, update relevant docs in the same PR:
- `README.md`
- `AGENTS.md`
- endpoint docs/comments as needed
