# Security Policy

## Supported Versions

VidKit is early-stage; security fixes are applied to `main`.

## Reporting a Vulnerability

Please do **not** open a public issue for sensitive vulnerabilities.

Report privately via GitHub Security Advisories:
- Go to the repository
- Open **Security** → **Report a vulnerability**

Include:
- affected endpoint/file
- reproduction steps
- impact assessment
- suggested mitigation (if available)

## Security Principles

- Local-first processing for user media
- No hardcoded secrets in source
- No committing user media/voice content
- Validate model/tool availability and fail safely
- Prefer explicit error handling over silent failure

## Secret Handling

Never commit:
- API keys/tokens/private keys
- `.env` secrets
- credential dumps/logs

Use environment variables and local secret stores.

## Data Handling

- Runtime media/output folders must remain gitignored
- Avoid collecting/storing unnecessary PII
- Keep logs minimal and free of sensitive payload data
