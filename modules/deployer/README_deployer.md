# EVA Deployer — CI/CD self-update agent (`:8789`)

Eva keeps **herself** current. The Deployer is an event-driven (polling) CI/CD
agent that watches GitHub for new commits on `main` and, when the remote is
ahead, safely self-deploys: it fast-forwards the local checkout and gracefully
restarts only the Eva services whose module code changed.

> **Safety is paramount.** This auto-restarts a *running* Eva. Every guardrail
> here exists so a self-update can never break a live system.

## How it works

A resilient daemon loop (mirrors `modules/social-scheduler/loop.py`) starts on
FastAPI startup via the launcher `SERVICES.deployer` entry. Every **5 hours**
(configurable — see below) it runs one `check()` pass:

1. **Poll.** Resolve the remote head of `main` via
   `gh api repos/Mangotec333/Eva/commits/main --jq '.sha'` (falls back to
   `git ls-remote origin main`) and compare to local `HEAD`.
   - Equal → **no-op** (`up_to_date`).
   - Remote ahead → proceed to deploy.
2. **Safe pull.** `git fetch origin main` then `git merge --ff-only origin/main`.
   - Any conflict / non-fast-forward → **ABORT**: log `deploy_skipped_conflict`
     to eva-state, restart nothing, keep looping. We never merge, rebase, or
     force — git refuses a non-ff and the working tree is left untouched.
3. **Diff.** `git diff --name-only <old>..<new>` → map changed files at
   `modules/<dir>/…` to launcher `SERVICES` keys. Files outside `modules/`
   (root scripts, docs) map to nothing and restart nothing.
4. **Gated restart.** For each affected service, wait (bounded retries) until
   nothing is **in-flight** — if social-scheduler is firing a slot, a gate is
   awaiting approval, or a dispatch is running, we hold. Once free, restart that
   one service via the launcher (`POST /stop/{svc}` → `POST /start/{svc}`). If a
   service never goes idle within the bound, we **skip** its restart (leave a
   slightly-stale service running rather than kill it mid-task).
5. **Log.** Emit `deploy_applied` (services restarted, old→new SHA) or
   `deploy_failed` to eva-state (`:8769`).

The loop is **resilient** (every error caught, logged, emitted; the service
never crashes) and **offline-safe** (`EVA_DEPLOYER_OFFLINE=1` → every real
git/gh/launcher call is skipped and a check is a pure no-op).

### In-flight gate

A restart is held while any `*.lock` file exists in `EVA_INFLIGHT_LOCK_DIR`
(default `~/.eva/locks`). Agents that are mid-action drop a lock there; no
directory / no locks → free to restart.

## Scope

**Eva-repo self-update only** — `git pull` + restart changed Eva services. The
**eva-landing / Vercel deploy is intentionally out of scope**: that front-end is
handled separately by native Vercel auto-deploy (Vercel builds and ships on push
on its own). The Deployer never touches it.

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `EVA_DEPLOYER_POLL_INTERVAL_SECONDS` | `18000` (5h) | Loop cadence |
| `EVA_DEPLOYER_OFFLINE` | unset | `1` → loop no-ops, no real git/restart |
| `EVA_DEPLOYER_NO_LOOP` | unset | `1` → don't start the self-poll loop |
| `EVA_DEPLOYER_REPO` | `Mangotec333/Eva` | `owner/repo` for the SHA poll |
| `EVA_DEPLOYER_BRANCH` | `main` | Branch to track |
| `EVA_HOME` | `~/Eva` | Local checkout to pull + restart from |
| `EVA_LAUNCHER_URL` | `http://localhost:8768` | Launcher for restarts |
| `EVA_INFLIGHT_LOCK_DIR` | `~/.eva/locks` | In-flight lock directory |
| `EVA_STATE_URL` | `http://localhost:8769` | eva-state ledger |

**Secrets:** the GitHub token is **never** hardcoded. Remote-SHA lookup uses the
`gh` CLI (auth handled on the Mac via `gh auth`) or an authenticated
`git ls-remote`; `GITHUB_TOKEN` from the environment is honoured by both if set.

## HTTP surface (`:8789`)

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health + local SHA + poll interval + offline flag |
| GET | `/deployer/status` | Current SHA, last check, last result |
| POST | `/deployer/check` | Manually trigger one poll → safe self-deploy pass |
| GET | `/deployer/history` | Recent deploy passes (newest first) |

Also registered on the launcher `:8768` via lazy import
(`GET /deployer/status`, `POST /deployer/check`, `GET /deployer/history`).

## CLI

```bash
python cli.py status                 # current SHA + last check + last result
python cli.py check                  # one poll → safe self-deploy pass
python cli.py history --limit 20     # recent deploy passes (newest first)
```

## Tests

Fully offline — git, `gh`, the launcher, and the in-flight gate are all faked;
**no real git pull or service restart ever happens** in the suite.

```bash
cd modules/deployer && python3 test_deployer.py
```
