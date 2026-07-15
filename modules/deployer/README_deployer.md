# EVA Deployer — CI/CD self-update agent (`:8789`)

Eva keeps **everything** current. The Deployer is an event-driven (polling)
CI/CD agent that watches GitHub for new commits and, when a remote is ahead,
safely deploys it. It iterates a configurable list of **deploy targets** every
pass; each target names its own repo, branch, local path, and **action**:

  * **`eva`** (`pull_and_restart`) — the Eva backend repo. Fast-forward the local
    checkout and gracefully restart only the Eva services whose module code
    changed.
  * **`eva-landing`** (`vercel_prod`) — the marketing front-end. Fast-forward the
    local checkout and run `vercel --prod` (native Vercel production deploy).

> **Safety is paramount.** This auto-restarts a *running* Eva and ships a live
> site. Every guardrail here exists so a self-update can never break either.

## How it works

A resilient daemon loop (mirrors `modules/social-scheduler/loop.py`) starts on
FastAPI startup via the launcher `SERVICES.deployer` entry. Every **5 hours**
(configurable — see below) it runs one `check()` pass that iterates **all**
configured targets. Per target it resolves the remote head via
`gh api repos/<owner>/<repo>/commits/<branch> --jq '.sha'` (falls back to
`git ls-remote origin <branch>`) and compares to local `HEAD`:

  - Equal → **no-op** (`up_to_date`).
  - Remote ahead → dispatch by the target's `action`.

### Action: `pull_and_restart` (the `eva` repo)

1. **Safe pull.** `git fetch` then `git merge --ff-only origin/<branch>`.
   - Any conflict / non-fast-forward → **ABORT**: log `deploy_skipped_conflict`,
     restart nothing, keep looping. We never merge, rebase, or force — git
     refuses a non-ff and the working tree is left untouched.
2. **Diff.** `git diff --name-only <old>..<new>` → map changed files at
   `modules/<dir>/…` to launcher `SERVICES` keys. Files outside `modules/`
   (root scripts, docs) map to nothing and restart nothing.
3. **Gated restart.** For each affected service, wait (bounded retries) until
   nothing is **in-flight** — if social-scheduler is firing a slot, a gate is
   awaiting approval, or a dispatch is running, we hold. Once free, restart that
   one service via the launcher (`POST /stop/{svc}` → `POST /start/{svc}`). If a
   service never goes idle within the bound, we **skip** its restart (leave a
   slightly-stale service running rather than kill it mid-task).
4. **Log.** Emit `deploy_applied` (services restarted, old→new SHA) or
   `deploy_failed` to eva-state (`:8769`).

### Action: `vercel_prod` (the `eva-landing` repo)

1. **Safe pull.** Same `git merge --ff-only`. Any conflict / non-fast-forward /
   pull failure → **ABORT**: log `deploy_landing_failed`, **do not run vercel**
   (never ship a half-updated tree), keep looping.
2. **Deploy.** Run `vercel --prod --yes` inside the target's local path with the
   resolved token. On any non-zero exit / missing CLI → `deploy_landing_failed`
   (abort + log + skip; a broken build never ships).
3. **Log.** Emit `deploy_landing_applied` (old→new SHA, production URL) or
   `deploy_landing_failed` to eva-state (`:8769`).

The loop is **resilient** (every error caught, logged, emitted; the service
never crashes; one target crashing never stops the others) and **offline-safe**
(`EVA_DEPLOYER_OFFLINE=1` → every real git/gh/launcher/vercel call is skipped and
a check is a pure no-op).

### In-flight gate

A restart is held while any `*.lock` file exists in `EVA_INFLIGHT_LOCK_DIR`
(default `~/.eva/locks`). Agents that are mid-action drop a lock there; no
directory / no locks → free to restart.

## Deploy targets

The target list is resolved **config-file-primary**: the `deploy_targets` key in
`~/.eva/channels_config.json` → `EVA_DEPLOY_TARGETS` env (JSON) → the built-in
two-target default. Each target is `{"name", "repo", "path", "branch",
"action"}` (`branch` defaults to `main`, `action` to `pull_and_restart`, `~` in
`path` is expanded). Example:

```json
{
  "deploy_targets": [
    {"name": "eva", "repo": "Mangotec333/Eva", "path": "~/Eva",
     "branch": "main", "action": "pull_and_restart"},
    {"name": "eva-landing", "repo": "Mangotec333/eva-landing",
     "path": "~/eva-landing", "branch": "master", "action": "vercel_prod"}
  ]
}
```

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `EVA_DEPLOYER_POLL_INTERVAL_SECONDS` | `18000` (5h) | Loop cadence |
| `EVA_DEPLOYER_OFFLINE` | unset | `1` → loop no-ops, no real git/restart/vercel |
| `EVA_DEPLOYER_NO_LOOP` | unset | `1` → don't start the self-poll loop |
| `EVA_DEPLOY_TARGETS` | unset | JSON target list (config file wins over this) |
| `EVA_CHANNELS_CONFIG` | `~/.eva/channels_config.json` | Config-file source |
| `EVA_HOME` | `~/Eva` | Default local checkout for the `eva` target |
| `EVA_LAUNCHER_URL` | `http://localhost:8768` | Launcher for restarts |
| `EVA_INFLIGHT_LOCK_DIR` | `~/.eva/locks` | In-flight lock directory |
| `EVA_STATE_URL` | `http://localhost:8769` | eva-state ledger |

**Secrets:** never hardcoded. The GitHub token comes from the `gh` CLI (auth on
the Mac via `gh auth`) or an authenticated `git ls-remote` (`GITHUB_TOKEN` from
the env is honoured by both). The **Vercel token** is resolved config-file-first:
`{"vercel": {"token": …}}` (or `vercel_token`) in `~/.eva/channels_config.json`,
falling back to the `VERCEL_TOKEN` env var.

## HTTP surface (`:8789`)

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health + targets + poll interval + offline flag |
| GET | `/deployer/status` | Targets, last check, last result |
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
