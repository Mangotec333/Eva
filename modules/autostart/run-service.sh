#!/bin/bash
# ─────────────────────────────────────────────────────────────────
#  EVA Service Runner
#  Called by launchd plists — sources shell env so Python packages
#  are found regardless of install method (Homebrew, pyenv, etc.)
#
#  Usage: run-service.sh <module-dir> <script.py>
#  e.g.:  run-service.sh content-engine main.py
# ─────────────────────────────────────────────────────────────────

MODULE="$1"   # e.g. "content-engine"
SCRIPT="$2"   # e.g. "main.py"
EVA_HOME="$HOME/Eva"

# ── 1. Load shell environment (finds Homebrew, pyenv, conda Python) ─
# Source in order of likelihood
for rc in "$HOME/.zshrc" "$HOME/.bash_profile" "$HOME/.bashrc" "$HOME/.profile"; do
    [ -f "$rc" ] && source "$rc" 2>/dev/null && break
done

# ── 2. Resolve Python — prefer Homebrew/pyenv over system stub ──────
PYTHON=""
for candidate in \
    "$(which python3 2>/dev/null)" \
    "/opt/homebrew/bin/python3" \
    "/usr/local/bin/python3" \
    "$HOME/.pyenv/shims/python3" \
    "/usr/bin/python3"; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
        # Test that this Python can import fastapi (has our packages)
        if "$candidate" -c "import fastapi" 2>/dev/null; then
            PYTHON="$candidate"
            break
        fi
    fi
done

# Fallback to whatever python3 is on PATH even if packages missing
if [ -z "$PYTHON" ]; then
    PYTHON="$(which python3 2>/dev/null || echo /usr/bin/python3)"
fi

# ── 3. Log startup info for debugging ───────────────────────────────
echo "=== EVA $MODULE starting at $(date) ==="
echo "    Python:  $PYTHON ($($PYTHON --version 2>&1))"
echo "    Script:  $EVA_HOME/modules/$MODULE/$SCRIPT"
echo "    WorkDir: $EVA_HOME/modules/$MODULE"
echo ""

# ── 4. Run the service ───────────────────────────────────────────────
cd "$EVA_HOME/modules/$MODULE" || { echo "ERROR: directory not found: $EVA_HOME/modules/$MODULE"; exit 1; }
exec "$PYTHON" "$SCRIPT"
