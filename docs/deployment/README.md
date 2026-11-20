# Deployment documentation

Living notes for getting StudyForge into production environments.

Update these files as decisions change. Prefer short, dated changelog
entries over rewriting history.

## Contents

| File | Purpose |
|------|---------|
| [frontend-vercel-deployment.md](./frontend-vercel-deployment.md) | SCRUM-126: React/Vite on Vercel, `/api` proxy, env, Google OAuth, CI/CD, troubleshooting |
| [backend-oracle-deployment.md](./backend-oracle-deployment.md) | SCRUM-125: Django backend, Postgres + pgvector, and Redis on Oracle OCI (+ `scripts/deploy-oci.sh`) |
| [production-document-storage.md](./production-document-storage.md) | SCRUM-127: private object storage, service connections, cutover, and probes |

## Frontend vs backend deploy

| Layer | Host | How it updates |
|-------|------|----------------|
| React frontend | Vercel | Git push to the Vercel production branch → auto build/deploy |
| Django API | OCI VM | `scripts/deploy-oci.sh` over SSH (Bitbucket Pipeline auto-deploy when minutes allow) |

## How to update

1. Record what was actually done (console clicks, commands, env var names).
2. Note blockers and the fix that unblocked them.
3. Keep secrets out of these docs — use placeholders like `<POSTGRES_PASSWORD>`.
4. When a step is verified, mark it in the runbook checklist.

## Secrets (OCI)

Production env for SCRUM-125 lives **only on the VM** at `/etc/studyforge.env`
(mode `600`). See [backend-oracle-deployment.md](./backend-oracle-deployment.md) for how to
SSH, view/edit, and restart services. Never commit that file.

## Related repo docs

- Local Postgres/Redis Compose: root [README.md](../../README.md)
- Auth / cookie production notes: [authentication-design.md](../authentication-design.md)
- Document processing worker (local kind): [kind-local-worker.md](../kind-local-worker.md)
- Frontend Vercel deployment (SCRUM-126): [frontend-vercel-deployment.md](./frontend-vercel-deployment.md)
- Backend Oracle deployment (manual + planned Bitbucket auto-deploy + processing options): [backend-oracle-deployment.md](./backend-oracle-deployment.md)
