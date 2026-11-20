# Frontend Vercel deployment (SCRUM-126)

**Ticket:** Deploy frontend with public domain, HTTPS, CI/CD and Google OAuth
production setup  
**Parent:** SCRUM-93 Project Setup  
**Target:** Vercel (static React / Vite SPA)  
**Status:** Production cutover verified on feature branch; custom domain deferred  

**Production frontend URL:** `https://studyforge-frontend-nine.vercel.app`  
**Production API (origin):** `https://studyforge-rodians.duckdns.org`  
**Browser API base (via Vercel proxy):** `/api/v1`  
**Health via proxy:** `GET https://studyforge-frontend-nine.vercel.app/api/v1/health/`
→ `{"status": "ok"}`

## Goal

Make the StudyForge React app publicly reachable over HTTPS, talk to the
production Django API without CORS/cookie breakage, auto-deploy on git push,
and support email + Google sign-in on the production origin.

## Target architecture

```text
Browser
  │
  ├─ UI (HTML/JS/CSS)
  │     → Vercel CDN
  │         https://studyforge-frontend-nine.vercel.app
  │
  └─ API calls to same origin: /api/v1/...
        → Vercel rewrite (frontend/vercel.json)
              → https://studyforge-rodians.duckdns.org/api/...
                    → Nginx → Gunicorn → Django (OCI)
                         → Postgres / Redis
```

**Why same-origin `/api` proxy**

- Frontend and API are on different hosts (Vercel vs DuckDNS).
- Auth uses CSRF + HttpOnly refresh cookies (`SameSite=Lax`).
- The browser cannot read a CSRF cookie set on DuckDNS from a Vercel page.
- Proxying `/api` through Vercel makes cookies first-party to the frontend host.
- Django still runs only on OCI; Vercel does not host the backend.

**What Vercel does *not* host**

- Django, Postgres, Redis, or the document-processing worker.
- Deploying the worker later requires OCI/worker config only — no Vercel env
  changes for processing itself.

## Acceptance criteria (from ticket)

- [x] App loads at a public HTTPS URL (Vercel `*.vercel.app`; custom domain later)
- [x] Frontend talks to production backend without CORS errors (via `/api` proxy)
- [x] Push to the configured production branch triggers Vercel build + deploy
- [x] Email sign-in works on the production origin
- [x] Google sign-in works on the production origin (OAuth Web client + env)
- [x] Client-side routing: refresh on deep links serves the SPA (not a Vercel 404)
- [ ] Custom public domain (deferred — see [Custom domain later](#custom-domain-later))

## Repo configuration

### `frontend/vercel.json`

Checked into the repo under `frontend/` (Vercel **Root Directory** = `frontend`):

```json
{
  "rewrites": [
    {
      "source": "/api/:path(.*)",
      "destination": "https://studyforge-rodians.duckdns.org/api/:path"
    },
    {
      "source": "/((?!api/).*)",
      "destination": "/index.html"
    }
  ]
}
```

| Rule | Purpose |
|------|---------|
| `/api/:path(.*)` → DuckDNS | Reverse-proxy API (including trailing slashes) |
| `/((?!api/).*)` → `/index.html` | SPA fallback; **excludes** `/api` so API never returns HTML |

**Pitfalls already hit in SCRUM-126**

| Symptom | Cause | Fix |
|---------|--------|-----|
| `Unexpected token '<', "<!doctype "...` | SPA catch-all served `index.html` for `/api` | Exclude `/api` from SPA rewrite |
| `/api/v1/health` → 301, `/api/v1/health/` → 404 | `:path*` did not match trailing slash | Use `/api/:path(.*)` |
| Backend OK on feature branch, 404 after switching Production to `development` | `development` lacked `vercel.json` | Keep Production on a branch that includes `vercel.json` until merge |

### Build settings (Vercel project)

| Setting | Value |
|---------|--------|
| Framework | Vite |
| Root Directory | `frontend` |
| Install | `npm install` / `npm ci` |
| Build | `npm run build` (`tsc -b && vite build`) |
| Output | `dist` |

### Git connection

- **Source of truth for the team:** Bitbucket `mth115_super/studyforge`
- Vercel project must be connected to that Bitbucket repo (not a stale fork).
- **GitHub is not required** for frontend deploy. Bitbucket Pipeline minutes are
  not used by Vercel builds.

**Current Production Branch Tracking (until SCRUM-126 merges):**  
`feature/SCRUM-126-frontend-deployment`

After merge into `development`, switch Branch Tracking to `development` (or a
dedicated `deployment` branch if the team prefers). Changing the branch alone
without `vercel.json` on that branch breaks `/api`.

## Environment variables

### Vercel (frontend) — Project → Settings → Environment Variables

| Key | Production value | Visibility | Notes |
|-----|------------------|------------|--------|
| `VITE_API_BASE_URL` | `/api/v1` | **Config** (not Secret) | Relative; same-origin proxy. Vite embeds at **build** time. |
| `VITE_GOOGLE_CLIENT_ID` | OAuth Web client ID | **Config** | Same value as backend `GOOGLE_OAUTH_CLIENT_ID`. Empty → Google button Unavailable. |

`VITE_*` variables cannot use Secret visibility on Vercel (they ship in the
browser bundle). If a var was saved as Secret by mistake: delete and recreate
as Config, then **redeploy**.

After any env change: **Redeploy** (Deployments → ⋮ → Redeploy). Push alone does
not rebuild with new env until a new deployment runs.

### Local laptop (not Vercel)

`frontend/.env` (gitignored), from `.env.example`:

```text
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_GOOGLE_CLIENT_ID=
```

Local uses the Django URL directly; production uses `/api/v1` + `vercel.json`.

### OCI backend (`/etc/studyforge.env`) — required for browser + auth

Set on the VM (never commit). At minimum for this frontend:

```text
CORS_ALLOWED_ORIGINS=https://studyforge-frontend-nine.vercel.app
CSRF_TRUSTED_ORIGINS=https://studyforge-frontend-nine.vercel.app
GOOGLE_OAUTH_CLIENT_ID=<same Web client ID as VITE_GOOGLE_CLIENT_ID>
```

Comma-separate additional origins if needed (preview URLs, later custom domain).
No trailing slash on origins.

After edits:

```bash
sudo systemctl restart studyforge-gunicorn
```

CORS still matters for any direct DuckDNS calls; the same-origin proxy is the
primary path for the SPA. CSRF trusted origins must include the frontend origin
for cookie auth flows.

See [backend-oracle-deployment.md](./backend-oracle-deployment.md) for SSH and
full env list.

## Initial project setup (checklist)

1. Create/import Vercel project from Bitbucket `mth115_super/studyforge`.
2. Set Root Directory `frontend`, Vite build/`dist` as above.
3. Add `VITE_API_BASE_URL=/api/v1` (Config).
4. Ensure `frontend/vercel.json` is on the branch Vercel builds.
5. Deploy; note the `*.vercel.app` production URL.
6. Update OCI `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` to that exact origin;
   restart Gunicorn.
7. Confirm `curl -i https://<vercel-host>/api/v1/health/` → JSON `{"status":"ok"}`.
8. Confirm email login on the live site.
9. Configure Google (below); set `VITE_GOOGLE_CLIENT_ID`; redeploy; set OCI
   `GOOGLE_OAUTH_CLIENT_ID`; restart Gunicorn; test Google login.
10. Set Production Branch Tracking; verify push → new Deployment.

## Google OAuth production setup

### Google Cloud Console

1. Project with StudyForge OAuth (APIs & Services → Credentials).
2. OAuth consent screen: **External** is correct for student Gmail accounts.
   While status is **Testing**, add Gmail addresses under **Test users**.
3. Create or edit **OAuth client ID** → type **Web application**.
4. **Authorized JavaScript origins** (no trailing slash):
   - `http://localhost:5173`
   - `https://studyforge-frontend-nine.vercel.app`
   - (add custom domain later)
5. Copy the **Client ID** only (not the client secret).

### Wire the same Client ID

| Place | Variable |
|-------|----------|
| Vercel | `VITE_GOOGLE_CLIENT_ID` |
| OCI `/etc/studyforge.env` | `GOOGLE_OAUTH_CLIENT_ID` |

Redeploy Vercel after the frontend env change; restart Gunicorn after the OCI
change.

## CI/CD (Vercel auto-deploy)

```text
git push origin <production-branch>
  → Bitbucket stores the commit
  → Vercel webhook
  → npm ci / build in frontend/
  → Production URL updates
```

- Does **not** consume Bitbucket Pipeline minutes.
- Does **not** require GitHub.
- Empty-commit verification used in SCRUM-126:
  `chore(SCRUM-126): verify Vercel auto-deploy on push`.

**Backend is separate:** pushing Django code does not update OCI until
[`scripts/deploy-oci.sh`](../../scripts/deploy-oci.sh) (or manual SSH) runs.
See [backend-oracle-deployment.md](./backend-oracle-deployment.md).

**Bitbucket Pipelines** remain useful for PR/branch **tests** when minutes
allow; they are not the frontend deploy mechanism.

### Switching Production branch to `development` later

1. Merge SCRUM-126 (including `frontend/vercel.json`) into `development`.
2. Vercel → Environments → Production → Branch Tracking → `development`.
3. Confirm a new deploy; `curl` `/api/v1/health/` on the production host.

Do not point Production at `development` before `vercel.json` exists there.

## Smoke tests

### Proxy / API

```bash
# Must be JSON, not HTML, not Vercel NOT_FOUND
curl -i https://studyforge-frontend-nine.vercel.app/api/v1/health/

# Origin API still healthy
curl -i https://studyforge-rodians.duckdns.org/api/v1/health/
```

### Browser

1. Open production URL over HTTPS; hard-refresh.
2. Footer/health should show backend connected (not “Failed to fetch” / HTML parse errors).
3. Refresh `/login`, `/register`, and an authenticated deep link — no Vercel 404.
4. Email login and logout.
5. Google button not “Unavailable”; sign-in with a consent-screen test user.

### After each frontend env change

Redeploy, then repeat health + login checks.

## Troubleshooting

| Symptom | Likely cause | What to do |
|---------|--------------|------------|
| Backend unavailable / Failed to fetch | Wrong `VITE_API_BASE_URL`, CORS, or API down | Check Network tab; curl DuckDNS health; verify OCI CORS for the exact origin if calling DuckDNS directly |
| `Unexpected token '<'` / doctype JSON error | `/api` returned `index.html` | Confirm `vercel.json` excludes `/api` from SPA; redeploy that commit |
| `/api/...` → `NOT_FOUND` | Proxy missing or branch without `vercel.json` | Switch Production branch or merge `vercel.json`; curl with trailing slash |
| Login: “Something went wrong on our side” | CSRF cookie not readable cross-site | Keep `VITE_API_BASE_URL=/api/v1` + proxy; do not point the SPA at DuckDNS directly |
| Google Unavailable | Missing `VITE_GOOGLE_CLIENT_ID` or no redeploy | Set Config env; redeploy |
| Google blocked / app not verified | Consent screen Testing | Add account under Test users |
| Google 503 from API | OCI `GOOGLE_OAUTH_CLIENT_ID` empty | Set on VM; restart Gunicorn |
| Env save error for `VITE_*` | Saved as Secret | Delete; recreate as Config |
| Bitbucket “No repositories found” in Vercel | OAuth/workspace access or Hobby/org limits | Re-auth Bitbucket; Admin on repo; or connect the workspace that owns `mth115_super/studyforge` |

## Document processing (future)

When the processing worker is deployed on OCI:

- **No Vercel changes** required for the worker itself.
- Frontend already talks only to Django; Django enqueues Redis jobs.
- Align `PROCESSING_SERVICE_TOKEN`, broker URL, and storage on the VM/worker.
- Optionally redeploy frontend only if new UI ships in the same release.

## Custom domain later

Deferred for SCRUM-126 cutover. When ready:

1. Vercel → Project → **Domains** → add hostname → configure DNS (A/CNAME as Vercel shows).
2. Wait for HTTPS (automatic on Vercel).
3. Update OCI:
   ```text
   CORS_ALLOWED_ORIGINS=https://<custom-domain>
   CSRF_TRUSTED_ORIGINS=https://<custom-domain>
   ```
   Restart Gunicorn. Keep or drop the old `*.vercel.app` origins as needed.
4. Google Cloud → OAuth Web client → Authorized JavaScript origins → add
   `https://<custom-domain>` → Save.
5. No change to `VITE_API_BASE_URL` if it stays `/api/v1` (relative).
6. Smoke-test health, email login, Google login, and SPA refresh on the new host.

## Related docs

- [backend-oracle-deployment.md](./backend-oracle-deployment.md) — OCI API, env file, `deploy-oci.sh`
- [production-document-storage.md](./production-document-storage.md) — S3 / storage for documents
- [authentication-design.md](../authentication-design.md) — cookie / JWT auth notes
- [api-contract.md](../api-contract.md) — auth and Google endpoint contracts
- Root [README.md](../../README.md) — local Compose and app overview

## Decisions log

| Date | Decision | Why |
|------|----------|-----|
| 2026-11-18 | Host SPA on Vercel; API stays on OCI | Matches SCRUM-125/126 split ownership |
| 2026-11-18 | `VITE_API_BASE_URL=/api/v1` + `vercel.json` proxy | Cross-site CSRF cookies break with direct DuckDNS calls |
| 2026-11-18 | SPA rewrite must exclude `/api` | Prevents HTML-as-JSON health failures |
| 2026-11-19 | Prefer Bitbucket over GitHub for Vercel Git | Team source of truth; no GitHub required for deploy |
| 2026-11-20 | Production Branch = feature branch until merge | `development` lacked `vercel.json`; switch after merge |
| 2026-11-20 | Defer custom domain | Ticket AC met with `*.vercel.app`; domain can follow |
| 2026-11-20 | Vercel auto-deploy = frontend CI/CD | Avoids Bitbucket Pipeline minute limits for deploy |

## Changelog

| Date | Change |
|------|--------|
| 2026-11-20 | Created this SCRUM-126 Vercel frontend runbook |
