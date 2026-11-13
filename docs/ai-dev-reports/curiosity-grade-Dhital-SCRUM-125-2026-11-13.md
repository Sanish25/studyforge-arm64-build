# Curiosity Grade — Dhital, SCRUM-125 (2026-11-13)

- Report graded: `curiosity-report-Dhital-SCRUM-125-2026-11-13.md`
- Student: Aashish Dhital (`wor21`)
- Assignment: SCRUM-125 — Deploy backend, Postgres with pgvector, and Redis to production (Oracle OCI)
- Self-context (ungraded): blank

## 1. Executive summary

The student completed SCRUM-125 by deploying the Django API with Postgres/pgvector and Redis on an Oracle OCI VM, then finishing HTTPS (DuckDNS + Certbot), iptables for ports 80/443, Gunicorn/Celery systemd units, and a persist check after restarting Gunicorn. The transcript combines a prior permanent full-chat export (OCI networking through Nginx HTTP and production settings) with a continuation session (domain, HTTPS, Celery, docs). Curiosity shows up as clarifying OCI/networking concepts, challenging one-VM vs split and auto-deploy claims, asking why/tradeoffs (production settings, Certbot vs Cloudflare, Celery-before-Redis), and probing some failures (SSH/Wi‑Fi, 502 after restart) while accepting first fixes on several other error episodes. Documentation was updated to `docs/deployment/backend-oracle-deployment.md`; `packaging` was added to requirements; Bitbucket auto-deploy and document-processing production deploy were deferred until after the frontend.

## 2. Curiosity rubric

Four raw scores (no composite): **(i) 3 · (ii) 3 · (iii) 3 · (iv) 2**

### (i) Clarification / requests for detail — **3**

- **Evidence (Part A, student turn ~line 402):** “if all are running inside the same VM as Django why do we need a private subnet at all. alsoexplain more about submnet and what it doe s”
- **Evidence (Part A, ~line 6468):** “Next: Nginx (public access) … what does that mean and what is nginx”
- **Evidence (Part B, ~line 6974):** “Nginx = terminates TLS on the VM (decrypts HTTPS) what does it mean”
- **Evidence (Part B, ~line 6864):** “what exactly is dns?”
- **Depth:** Best instances are consequential clarifications that pin down architecture (private subnet unnecessary on one-VM plan) and TLS termination after Certbot/Cloudflare discussion — not bare “explain more.” Follow-ups scope what the AI’s terms mean in the student’s concrete deploy path.
- **Events (ungraded count):** 22

### (ii) Challenge / skepticism [PRIORITY] — **3**

- **Evidence (Part A, ~line 566):** “are we putting everything in one VM? isnt it better pravctice to divide it”
- **Evidence (Part A, ~line 5335):** “are all of these cntainer in cloud i saw only two for db and redis”
- **Evidence (Part B, ~line 7034):** “OCI VM: UNCHANGED until someone SSHs and pulls so no matter somone always has to manually pull?”
- **Evidence (Part B, ~line 7064):** “[restart gunicorn then immediate HTTPS curl → 502 Bad Gateway] wasnt it supposed to be 200?”
- **Depth:** One-VM pushback tests the AI’s deploy topology against industry practice and redirects to an explicit tradeoff answer. Container observation verifies the AI’s “services” claim against what the student saw. Auto-deploy follow-up tests the merge≠ship claim. The 502 question challenges the expected persist-check outcome rather than accepting a silent failure.
- **Events (ungraded count):** 9
- **Supporting evidence:** Evidence Appendix shows student-run `dig`, `curl` (HTTP/HTTPS health), `nc` to port 22, `systemctl`/`journalctl`, and iptables checks grounding AI suggestions.

### (iii) Why / tradeoffs — **3**

- **Evidence (Part A, ~line 2358):** “why do we need to change Django’s settings for production? Can’t we use the same settings as our local setup?”
- **Evidence (Part A, ~line 2674):** “What “automatic production” would mean (you don’t have this yet) is this a better practice?”
- **Evidence (Part B, ~line 6968):** “relate this to how cloudfare work”
- **Evidence (Part B, ~line 7004):** “what happens if celery strats working before redis? will it break”
- **Depth:** Explicit why/better-practice questions on production settings and auto-deploy, plus Certbot-vs-Cloudflare comparison and Celery-before-Redis failure-mode tradeoff — weighs real deploy choices, not only how-to steps.
- **Events (ungraded count):** 10

### (iv) Error-response behavior [PRIORITY] — **2**

- **Evidence (PROBED — SSH episode, ~line 3543):** “whats the issue ? help me understand”
- **Evidence (PROBED — SSH episode, ~line 4826):** “okay is it because i am on a public unsecured wifi?”
- **Evidence (PROBED — 502 episode, ~line 7064):** “wasnt it supposed to be 200?”
- **Evidence (ACCEPTED pattern — packaging / Mac-vs-VM / dump fixes, ~lines 6992–7076):** student pastes Celery/`packaging`/`auth_user`/404 output and proceeds with AI’s first fixes (“[After pip install packaging] … now check”) without asking why those failures occurred before applying.
- **Depth:** Best probes are substantive: requesting explanation of SSH failure and offering a Wi‑Fi hypothesis; challenging 502 against the expected 200 after Gunicorn restart. Many other episodes are report-and-accept. Not quite the calibration bar for a single incisive redesign-level challenge of a wrong fix.
- **Events (ungraded count):** 10 episodes (see tally)

**Error episodes:** 10 (PROBED 2, ACCEPTED 8, LOOPED 0)

| # | Episode (from report §3) | Label |
|---|--------------------------|-------|
| 1 | SSH / OCI connectivity (placeholder IP, timeouts, Cloud Shell vs Mac) | PROBED |
| 2 | DuckDNS NXDOMAIN before successful registration | ACCEPTED |
| 3 | zsh `parse error near ')'` on Mac paste | ACCEPTED |
| 4 | Public port 80 unreachable while localhost Nginx 200 (iptables) | ACCEPTED |
| 5 | Cloud Shell `curl 127.0.0.1` connection refused (wrong host) | ACCEPTED |
| 6 | Immediate HTTPS 502 after Gunicorn restart | PROBED |
| 7 | `127.0.0.1` health 404 after Certbot `server_name` | ACCEPTED |
| 8 | `relation "auth_user" does not exist` | ACCEPTED |
| 9 | Celery `ModuleNotFoundError: packaging` | ACCEPTED |
| 10 | Mac-side `.venv` / `/etc/studyforge.env` / `celery` failures | ACCEPTED |

## 3. Notes for the grader (neutral)

Curiosity concentrated on OCI networking concepts (VCN/subnet/SSH/iptables), production Django config and deploy flow (manual vs auto), HTTPS/DNS/TLS terminology, and Celery/Redis startup ordering. Large stretches are step-following (“done,” “whats next,” paste terminal output, apply AI commands) after agreements were reached — description of workflow style, not a fault. Self-context field is blank and does not affect scores.

## 4. AI Sycophancy — No grade impact, for your awareness

- **Flattery:** AI opens a subnet answer with “Great question — for **our one-VM plan, you do not need the private subnet**” (Part A, ~line 406).
- **Held ground (positive):** On one-VM vs split, the AI agreed industry often separates tiers but kept one VM as the right fit for SCRUM-125 / Always Free — did not abandon the ticket-scoped plan under pressure.
- **Plausible agreement (not an incorrect cave):** Student hypothesized public Wi‑Fi as the SSH path problem; AI said “Very likely, yes” given Cloud Shell worked and Mac timed out — consistent with the evidence, not folding under a wrong technical claim.
- **No observed case** of the AI caving to an *incorrect* student technical claim in this report.

## 5. Performativity (preliminary)

Questions are tied to concrete StudyForge/OCI artifacts (private subnet on one VM, DuckDNS, iptables before REJECT, Certbot vs Cloudflare, Bitbucket merge vs VM pull, Celery before Redis, 502 after `systemctl restart studyforge-gunicorn`). Several change or lock decisions (one VM + Docker; park auto-deploy after frontend; persist iptables; install `packaging`). This does not look like generic filler questioning.

*This is a preliminary signal, not a definitive judgment of intent.*

## 6. CSV score-row

```csv
student_id,student_name,assignment,dim_i,dim_ii,dim_iii,dim_iv,events_i,events_ii,events_iii,err_episodes,probed,accepted,looped,date
wor21,Aashish Dhital,SCRUM-125,3,3,3,2,22,9,10,10,2,8,0,2026-11-13
```
