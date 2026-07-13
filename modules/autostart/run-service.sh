#!/bin/bash
# ─────────────────────────────────────────────────────────────────
#  EVA Service Runner (self-healing)
#  Called by launchd plists. Responsibilities:
#    1. Source shell env so the right Python (Homebrew/pyenv/venv) is used
#    2. Wait for the EVA Launcher (:8768) with backoff before binding
#       — removes the chicken-and-egg race at login
#    3. Clear a stale listener on our own port before binding
#       — prevents "address already in use" KeepAlive thrash
#    4. Run the service as a child and record a status file that
#       eva-status.sh reads, so state becomes a real up/down + reason
#
#  Usage: run-service.sh <module-dir> <script.py> [label] [bind_port]
#    e.g. run-service.sh logger eva_context_api.py context-api 8765
#
#  Tunables (env, all optional):
#    EVA_LAUNCHER_PORT   launcher readiness port          (default 8768)
#    EVA_LAUNCHER_WAIT   max seconds to wait for launcher (default 120)
#    EVA_PORT_CLEAR      1 = free stale port before bind  (default 1)
# ─────────────────────────────────────────────────────────────────

MODULE="$1"                 # e.g. "content-engine"
SCRIPT="$2"                 # e.g. "main.py"
LABEL="${3:-$MODULE}"       # launchd label suffix, e.g. "context-api"
BIND_PORT="${4:-}"          # TCP port this service binds (optional)

EVA_HOME="$HOME/Eva"
LOG_DIR="$EVA_HOME/logs"
STATUS_DIR="$LOG_DIR/status"
STATUS_FILE="$STATUS_DIR/$LABEL.status"

EVA_LAUNCHER_PORT="${EVA_LAUNCHER_PORT:-8768}"
EVA_LAUNCHER_WAIT="${EVA_LAUNCHER_WAIT:-120}"
EVA_PORT_CLEAR="${EVA_PORT_CLEAR:-1}"

mkdir -p "$STATUS_DIR" 2>/dev/null

# ── Status file helper ──────────────────────────────────────────────
# Writes a small key=value snapshot that eva-status.sh reads.
write_status() {
    local state="$1"
    local reason="${2:-}"
    local tmp="$STATUS_FILE.tmp.$$"
    {
        echo "label=$LABEL"
        echo "module=$MODULE"
        echo "script=$SCRIPT"
        echo "port=${BIND_PORT:-}"
        echo "state=$state"
        echo "reason=$reason"
        echo "pid=${SERVICE_PID:-}"
        echo "ts=$(date '+%Y-%m-%dT%H:%M:%S%z')"
        echo "epoch=$(date +%s)"
    } > "$tmp" 2>/dev/null && mv "$tmp" "$STATUS_FILE" 2>/dev/null
}

# ── TCP port check (no external deps — uses bash /dev/tcp) ───────────
port_open() {
    local port="$1"
    (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null && exec 3>&- 2>/dev/null
}

# ── Free a stale listener on a port before we try to bind ───────────
free_port() {
    local port="$1"
    port_open "$port" || return 0     # nothing there — good
    local pids
    pids=$(lsof -ti "tcp:$port" 2>/dev/null)
    if [ -n "$pids" ]; then
        echo "    Port :$port busy (pids: $pids) — clearing stale listener"
        kill $pids 2>/dev/null || true
        sleep 1
        pids=$(lsof -ti "tcp:$port" 2>/dev/null)
        [ -n "$pids" ] && { kill -9 $pids 2>/dev/null || true; sleep 1; }
    fi
}

# ── Wait for the Launcher (:8768) with capped exponential backoff ────
wait_for_launcher() {
    local deadline=$(( $(date +%s) + EVA_LAUNCHER_WAIT ))
    local delay=1
    while [ "$(date +%s)" -lt "$deadline" ]; do
        if port_open "$EVA_LAUNCHER_PORT"; then
            return 0
        fi
        write_status "waiting" "launcher :$EVA_LAUNCHER_PORT not up yet"
        sleep "$delay"
        delay=$(( delay * 2 ))
        [ "$delay" -gt 8 ] && delay=8
    done
    return 1
}

write_status "starting" "wrapper launched"

# ── 1. Load shell environment (finds Homebrew, pyenv, conda Python) ─
for rc in "$HOME/.zshrc" "$HOME/.bash_profile" "$HOME/.bashrc" "$HOME/.profile"; do
    [ -f "$rc" ] && source "$rc" 2>/dev/null && break
done

# ── 2. Resolve Python — prefer an interpreter that has our packages ──
PYTHON=""
for candidate in \
    "$EVA_HOME/modules/$MODULE/venv/bin/python3" \
    "$EVA_HOME/venv/bin/python3" \
    "$(which python3 2>/dev/null)" \
    "/opt/homebrew/bin/python3" \
    "/usr/local/bin/python3" \
    "$HOME/.pyenv/shims/python3" \
    "/usr/bin/python3"; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
        if "$candidate" -c "import fastapi" 2>/dev/null; then
            PYTHON="$candidate"
            break
        fi
    fi
done
if [ -z "$PYTHON" ]; then
    PYTHON="$(which python3 2>/dev/null || echo /usr/bin/python3)"
fi

# ── 3. Log startup info for debugging ───────────────────────────────
echo "=== EVA $LABEL ($MODULE/$SCRIPT) starting at $(date) ==="
echo "    Python:  $PYTHON ($($PYTHON --version 2>&1))"
echo "    WorkDir: $EVA_HOME/modules/$MODULE"
echo "    Port:    ${BIND_PORT:-none}"
echo ""

# ── 4. Deterministic ordering: wait for the Launcher first ──────────
#     The launcher itself provides :8768, so it must NOT wait on itself.
if [ "$LABEL" != "launcher" ] && [ "$MODULE" != "launcher" ]; then
    echo "    Waiting for EVA Launcher on :$EVA_LAUNCHER_PORT (up to ${EVA_LAUNCHER_WAIT}s)..."
    if wait_for_launcher; then
        echo "    ✓ Launcher reachable — proceeding"
    else
        echo "    ✗ Launcher not reachable after ${EVA_LAUNCHER_WAIT}s — exiting for retry"
        write_status "waiting" "launcher :$EVA_LAUNCHER_PORT unreachable after ${EVA_LAUNCHER_WAIT}s"
        # Exit non-zero; launchd KeepAlive/ThrottleInterval will relaunch us.
        exit 75   # EX_TEMPFAIL
    fi
fi

# ── 5. Clear a stale listener on our own port before binding ────────
if [ -n "$BIND_PORT" ] && [ "$EVA_PORT_CLEAR" = "1" ]; then
    free_port "$BIND_PORT"
fi

# ── 6. Run the service as a child so we can record why it exits ─────
cd "$EVA_HOME/modules/$MODULE" || {
    write_status "crashed" "module directory not found: $EVA_HOME/modules/$MODULE"
    echo "ERROR: directory not found: $EVA_HOME/modules/$MODULE"
    exit 1
}

write_status "running" "service process started"
"$PYTHON" "$SCRIPT" &
SERVICE_PID=$!
write_status "running" "pid $SERVICE_PID"

# Forward termination from launchd to the child for a clean shutdown.
trap 'kill -TERM "$SERVICE_PID" 2>/dev/null' TERM INT

wait "$SERVICE_PID"
CODE=$?

if [ "$CODE" -eq 0 ]; then
    write_status "stopped" "exited cleanly (code 0)"
else
    write_status "crashed" "exited code $CODE — see $LOG_DIR/eva-$LABEL.error.log"
fi
echo "=== EVA $LABEL exited with code $CODE at $(date) ==="
exit "$CODE"
