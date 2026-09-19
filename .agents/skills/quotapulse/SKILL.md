---
name: quotapulse
description: Use QuotaPulse to monitor provider balances and quotas, diagnose provider health, maintain runway calculations, and safely release or deploy the service.
metadata:
  short-description: Operate QuotaPulse safely
---

# QuotaPulse

Use this skill for QuotaPulse provider integrations, balance/quota alerts, history and runway behavior, dashboard changes, releases, or deployment diagnosis.

## Core boundaries

Never print, copy, or expose `.env`, API keys, OAuth tokens, database credentials, webhook secrets, or token-store contents. Read only the specific non-secret setting needed for a diagnosis.

Preserve existing user changes. Use `apply_patch` for source edits. Do not use destructive Git resets or remove Docker data volumes. Removing a stopped container is acceptable only when the exact container and the no-volume impact have been confirmed and the action has been stated to the user.

Before an external write or deployment, run the relevant tests and state the target version. After deployment, verify the container health endpoint and image version.

## Provider semantics

- Ordinary balances and credits may use historical runway calculations.
- GLM is a quota percentage, not a cash balance. Select only the five-hour quota window identified by `unit=5` and `number=1`; do not choose a lower remaining percentage from weekly or monthly windows.
- GLM thresholds are percentages: `100` means full remaining quota and `0` means exhausted.
- Quota projects must not produce long-term burn rate, runway days, depletion dates, or spending-spike alerts because their percentage resets with the provider window.

When changing a provider parser, add a multi-window fixture proving the intended window wins and a malformed-response case. Do not silently fall back to another labelled quota window.

## Verification workflow

For Go changes:

```bash
go test ./...
go vet ./...
go build ./cmd/quotapulse
```

For UI changes:

```bash
npm --prefix ui run typecheck
npm --prefix ui test
npm --prefix ui run build
```

Also run `git diff --check`. Validate generated dashboard or embedded assets when touched.

## Release and deployment

Use a new semantic tag for every release. Never rewrite an existing release tag. The release workflow builds and publishes the multi-architecture image to GHCR.

The production deployment is `/home/imwl/balance-alert`. Pin `QUOTAPULSE_VERSION` in its `.env`, pull the exact image, and run `docker compose up -d`. Preserve `data/` and `logs/`; never remove volumes during an upgrade.

Health verification should include:

```bash
docker ps --filter name=quotapulse
curl --fail --silent http://127.0.0.1:8080/health
```

When diagnosing a public domain, test the local application first, then the reverse proxy. A healthy local `/health` with a public 502 usually indicates proxy upstream or network configuration, not a provider integration failure.

## User-facing behavior

Keep production documentation English-first and link `README.zh-CN.md` for Chinese readers. Use plain “generic webhook” in public descriptions while retaining `WEBHOOKWISE_*` configuration names for compatibility.

The dashboard brand is QuotaPulse and uses `Q` in the navigation icon and favicon. Do not reintroduce the old Balance Alert name in new UI or documentation.
