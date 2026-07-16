# EVA Local-Exec — the "Mac hands" layer

> Port **8790** · binds **127.0.0.1 only** · `source_surface = local-exec` · `track = infra`

A localhost-only service that lets Eva run shell commands on the Mac, **on
demand, safely**. This is a request/response exec primitive (not a polling
loop): Eva asks to run a command, and Local-Exec either auto-runs it (if it is on
a small allowlist of demonstrably-safe ops) or gates it behind a **one-tap Slack
approval**. Every run is secret-masked and fully audited.

This is the generalized **hands** layer. The [deployer](../deployer)'s scoped
CI/CD (ff-only pull + restart / `vercel --prod`) is a **future consumer** of this
exec primitive, not a dependency of it.

## Why this is safe (safety is paramount — this is Eva running shell on your Mac)

1. **Localhost-only bind.** Binds `127.0.0.1:8790`. A startup assertion
   (`assert_localhost_bind`) **refuses to bind to `0.0.0.0`** or any non-loopback
   host — it fails closed (won't start) rather than open. **Never** exposed via
   cloudflared / any tunnel.
2. **Allowlist of SAFE ops that auto-run** (no approval). Config-file-primary in
   `~/.eva/local_exec_allowlist.json`, with an in-code default. Matched by
   command **prefix + argument validation** (never a substring match):
   - `git pull` / `git status` / `git diff` / `git log`
   - `curl localhost:*` / `curl 127.0.0.1:*` (loopback only)
   - service restart via the launcher's own `/start|/stop|/restart` route on
     `:8768`
   - `vercel --prod` (only when `cwd` is a real git checkout)
   - env-file token swaps: a single `KEY=VALUE` append/replace via `sed`/`python`
     on `~/.eva/*.json` or `~/Eva/.env` (nothing else)
3. **Non-allowlisted → does NOT run.** It becomes a `pending` run, a one-tap
   approval request is posted to Slack (reusing
   [`social-publish`](../social-publish) `slack_client` + `credentials.build_cfg`
   and the founder approve channel), and the call waits for
   `POST /local-exec/approve`. Default **300s** timeout → auto-expire +
   `local_exec_expired`. It never runs unapproved.
4. **Secret masking.** Bearer tokens, API-key/secret/token/password assignments,
   AWS keys, Slack (`xox*`) / GitHub (`ghp_` / `github_pat_`) / OpenAI (`sk-`)
   tokens, and long high-entropy tokens are masked out of stdout/stderr **and**
   the echoed command/args before anything is returned or written to disk.
   `masked: true` is set if anything was redacted. **No raw secret is ever
   persisted.**
5. **No shell.** Commands run as an argv list with `shell=False`. Pipes,
   redirects, `;` / `&&`, and globbing are inert — one program, explicit args.
6. **Full audit.** Every run (allowlisted / approved / blocked / denied / failed
   / expired) is emitted to eva-state (`:8769`) as `local_exec_*` events and
   stored in local sqlite (`runs` table: ts, command, args, cwd, exit_code,
   stdout_masked, stderr_masked, duration, status, triggered_by).
7. **Resilient + offline-safe.** Every error is caught/logged; the service never
   crashes on a bad command. `EVA_LOCAL_EXEC_OFFLINE=1` → `/exec` returns a
   mocked no-op and **never** spawns a subprocess (the test / sandbox default).

## API

| Method | Route | Purpose |
|---|---|---|
| `POST` | `/local-exec/exec` | `{command, args?, cwd?, triggered_by?, timeout?}` → run (allowlisted) or gate. Returns `{ok, exit_code, stdout, stderr, duration, masked, status, run_id, rule}` |
| `GET`  | `/local-exec/status` | Service health + allowlist summary + run counts by status |
| `GET`  | `/local-exec/history?limit=N` | Recent audited runs, newest first (capped) |
| `POST` | `/local-exec/approve` | `{run_id, approved}` → approve/deny a pending run (one-tap gate) |
| `POST` | `/local-exec/approve/{run_id}?approved=` | Approval link target (posted to Slack) |
| `GET`  | `/health` | Health + offline flag + allowlist size |

The same surface is registered on the launcher (`:8768`) via lazy import.

## CLI

```bash
python cli.py exec git status                 # allowlisted → runs now
python cli.py exec -- git log --oneline -5    # -- passes flags through
python cli.py exec --cwd ~/eva-landing vercel --prod
python cli.py status
python cli.py history --limit 20
python cli.py approve <run_id>                # or: approve <run_id> --deny
```

## Env

| Var | Default | Meaning |
|---|---|---|
| `EVA_LOCAL_EXEC_OFFLINE` | unset | `1` → never spawn a subprocess; `/exec` is a mocked no-op |
| `EVA_LOCAL_EXEC_ALLOWLIST` | `~/.eva/local_exec_allowlist.json` | allowlist config path |
| `LOCAL_EXEC_DB` | `./local_exec.db` | sqlite audit path |
| `EVA_STATE_URL` | `http://localhost:8769` | eva-state ledger |
| `EVA_LAUNCHER_URL` | `http://localhost:8768` | launcher (approval link + restart target) |
| `SLACK_BOT_TOKEN` / `EVA_SLACK_REVIEW_CHANNEL` | — | one-tap approval Slack (via social-publish) |

## Tests

Offline, mock-only — `subprocess.run` is never allowed to run a real command:

```bash
cd modules/local-exec && python test_local_exec.py
```

Covers: allowlist match (each rule) + non-match; secret masking; offline no-op;
non-allowlist → pending → approve → runs; deny; approval expiry; eva-state audit
emits; localhost-bind assertion refuses `0.0.0.0`; runner resilience.
