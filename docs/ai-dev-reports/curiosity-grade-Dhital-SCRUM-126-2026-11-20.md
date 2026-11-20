# Curiosity Grade

## 1. Executive summary

The student deployed the StudyForge React/Vite frontend to Vercel against the existing OCI API (SCRUM-126), working through CORS, SPA routing, a same-origin `/api` proxy for CSRF cookies, Google OAuth Console setup, and Vercel git auto-deploy on the feature branch. Across a long multi-day session they asked many clarifying questions, challenged inconsistent routing advice (rewrite vs routes), weighed whether the API proxy is standard/safe, and reported repeated deploy/auth failures with curl evidence. Deliverables included `frontend/vercel.json`, `scripts/deploy-oci.sh`, and `docs/deployment/frontend-vercel-deployment.md`. Custom domain was deferred.

## 2. Curiosity rubric

**(i) Clarification / requests for detail — 2**  
- Events (ungraded): 12  
- Evidence: “@vercel.json (1-4) WHAT DOES THIS MEAN I MEAN WHATS THE USE OF index.html”  
- Evidence: “i mean wahts the difference when the key was suckdns to this” (after a vague “whats the difference?”)  
- Depth justification: Best instances scope what is unclear (SPA rewrite purpose; DuckDNS URL vs `/api/v1`) and follow up for a precise comparison—substantive engagement with the answer space, not bare “why?” only.

**(ii) Challenge / skepticism [PRIORITY] — 3**  
- Events (ungraded): 6  
- Evidence: “didnt it fail on rewrite and we changed it to routes?”  
- Evidence: “{ \"rewrites\": [ … \"source\": \"/(.*)\" … ] } this right?” (re-checking a config the session had already marked as failing)  
- Supporting verification: Evidence Appendix rows for live `/api` curl (HTML then `NOT_FOUND`) and empty-commit auto-deploy check.  
- Depth justification: Best instance tests the AI’s consistency after it flipped back to rewrites, exposing a real gap in the advice—incisive skepticism.

**(iii) Why / tradeoffs — 3**  
- Events (ungraded): 5  
- Evidence: “frontend and proxies API calls. is this the standard way is it safe?”  
- Evidence: “for CI/CD the pipeline test on bitbucket runs out, the free pack. that might create a problem right?”  
- Depth justification: Best instance weighs a real architectural/security tradeoff of the proposed proxy (not only how to click Vercel); Bitbucket-minutes question weighs a constraint against the proposed CI/CD path—incisive.

**(iv) Error-response behavior [PRIORITY] — 3**  
- Events (ungraded): 10 episodes (see tally)  
- Evidence: During proxy/HTML failures: “didnt it fail on rewrite and we changed it to routes?”; “any way we could test ?”; after login/CSRF fix proposal: “whata changes are we applying ? just adda. path/” and the safety question above; after `development` break: “so we essentially cannot do di/ci on development brnahc now?” / “do i just need to change the branch and it works?”  
- Depth justification: In several error episodes the student queried the fix strategy, asked for a test method, and probed implications of the diagnosis—not only report-and-apply. Depth of probing in the best episodes is incisive; LOOPED not observed.

### Dimension (iv) episode tally

Error episodes: 10 (PROBED 4, ACCEPTED 6, LOOPED 0)

| # | Episode (from report §3) | Label |
|---|--------------------------|-------|
| 1 | Backend unavailable / Failed to fetch | ACCEPTED |
| 2 | Vercel Secret→Config lock | ACCEPTED |
| 3 | Still backend unavailable (wrong branch/CORS) | ACCEPTED |
| 4 | Branch not found / wrong Git connection | PROBED (“how is vercel connected to github i logged in using bitbucket”) |
| 5 | Bitbucket no repositories found | ACCEPTED |
| 6 | Login CSRF / “Something went wrong” | PROBED (scoped changes + safety of proxy) |
| 7 | Doctype / HTML-as-JSON for `/api` | PROBED (rewrite vs routes; can we test) |
| 8 | curl `/api` `NOT_FOUND` (trailing slash) | ACCEPTED |
| 9 | Production→`development` backend disconnected | PROBED (CI on development? just change branch?) |
| 10 | Google Credentials empty / Audience / Test users | ACCEPTED (clarifications during setup; followed create flow) |

**Raw scores (no composite):** (i) 2 · (ii) 3 · (iii) 3 · (iv) 3

## 3. Notes for the grader (neutral)

Curiosity concentrated on deployment semantics (env vars, SPA vs proxy, Bitbucket vs Vercel vs OCI ownership) and on debugging live production failures. Procedural stretches (nano keys, commit messages, “web?” for OAuth type) often proceeded by confirming AI instructions. Several ACCEPTED error episodes still coexisted with later PROBED episodes on the same feature (proxy/routing).

Self-context: none provided.

## 4. AI Sycophancy — No grade impact, for your awareness

- No strong flattery patterns (“Great question!” / over-praise) stood out in the condensed transcript.
- On the rewrite↔routes flip, the student challenged correctly; the AI explained the difference rather than insisting the failed catch-all config was fine — hold/correct-under-challenge (positive).
- No observed case of the AI caving to an **incorrect** student factual challenge.

## 5. Performativity (preliminary)

Questions are tied to concrete artifacts (`vercel.json`, exact domains, curl `NOT_FOUND`, Bitbucket minutes, proxy safety), which looks task-driven rather than generic. *This is a preliminary signal, not a definitive judgment of intent.*

## 6. CSV score-row

```csv
student_id,student_name,assignment,dim_i,dim_ii,dim_iii,dim_iv,events_i,events_ii,events_iii,err_episodes,probed,accepted,looped,date
wor21,Aashish Dhital,SCRUM-126,2,3,3,3,12,6,5,10,4,6,0,2026-11-20
```
