#!/bin/bash
# EVA Bootstrap — run this ONCE manually to start the Launcher
# After this, all other services auto-start via launchd
# Solves the chicken-and-egg problem: Sentinel needs launchd, Launcher needs a first push.

echo "🚀 EVA Bootstrap starting..."
source ~/.zshrc 2>/dev/null || true
EVA_HOME="$HOME/Eva"

# ── Find working Python with FastAPI ────────────────────────────
PYTHON=""
for p in \
    "$HOME/.pyenv/shims/python3" \
    "$HOME/anaconda3/bin/python3" \
    "$HOME/miniconda3/bin/python3" \
    "/usr/local/bin/python3" \
    "/opt/homebrew/bin/python3" \
    "/usr/bin/python3"; do
    if [ -f "$p" ] && "$p" -c "import fastapi" 2>/dev/null; then
        PYTHON="$p"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "❌ No Python with FastAPI found. Installing..."
    pip3 install fastapi uvicorn 2>/dev/null || pip install fastapi uvicorn
    PYTHON=$(which python3)
fi

echo "✅ Using Python: $PYTHON"

# ── Start Launcher on port 8768 ──────────────────────────────────
mkdir -p "$EVA_HOME/logs"
cd "$EVA_HOME/modules/launcher"
echo "Starting Launcher on :8768..."
nohup "$PYTHON" -m uvicorn eva_launcher:app --host 0.0.0.0 --port 8768 \
    > "$HOME/Eva/logs/eva-launcher.log" 2>&1 &
echo "Launcher PID: $!"

# ── Wait and verify ──────────────────────────────────────────────
sleep 3
if nc -z localhost 8768 2>/dev/null; then
    echo "✅ Launcher online at :8768"
    echo ""
    echo "Next step — install all services:"
    echo "  bash ~/Eva/modules/autostart/eva-install-services.sh"
    echo ""
    echo "Or run Sentinel directly:"
    echo "  python3 ~/Eva/modules/angels/angel0_sentinel/sentinel.py"
else
    echo "⚠️  Launcher may still be starting. Check:"
    echo "  tail -f ~/Eva/logs/eva-launcher.log"
fi
