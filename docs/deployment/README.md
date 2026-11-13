# Deployment documentation

Living notes for getting StudyForge into production environments.

Update these files as decisions change. Prefer short, dated changelog
entries over rewriting history.

## Contents

| File | Purpose |
|------|---------|
| [backend-oracle-deployment.md](./backend-oracle-deployment.md) | SCRUM-125: Django backend, Postgres + pgvector, and Redis on Oracle OCI |

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
- Backend Oracle deployment (manual + planned Bitbucket auto-deploy + processing options): [backend-oracle-deployment.md](./backend-oracle-deployment.md)
