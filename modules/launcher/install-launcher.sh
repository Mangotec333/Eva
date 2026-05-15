#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  EVA Launcher — Module 7 Install Script
#  Run once from your Mac:  bash ~/Eva/modules/launcher/install-launcher.sh
# ─────────────────────────────────────────────────────────────────

set -e

CYAN='\033[0;36m'; BOLD='\033[1m'; GREEN='\033[0;32m'; RESET='\033[0m'
USERNAME=$(whoami)
EVA_HOME="$HOME/Eva"
LAUNCHER_DIR="$EVA_HOME/modules/launcher"
PLIST_SRC="$LAUNCHER_DIR/com.mangotec.eva-launcher.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.mangotec.eva-launcher.plist"
LOG_DIR="$EVA_HOME/logs"

echo -e "${CYAN}${BOLD}"
echo "  EVA Launcher — Module 7 Setup"
echo -e "${RESET}"

# ── 1. Create logs dir ───────────────────────────────────────────
mkdir -p "$LOG_DIR"
echo "  ✓ Log directory: $LOG_DIR"

# ── 2. Install Python deps ───────────────────────────────────────
echo "  → Installing Python dependencies…"
pip3 install -q -r "$LAUNCHER_DIR/requirements.txt"
echo "  ✓ Dependencies installed"

# ── 3. Patch plist with real username ───────────────────────────
sed "s/REPLACE_USERNAME/$USERNAME/g" "$PLIST_SRC" > "$PLIST_DEST"
echo "  ✓ Plist installed → $PLIST_DEST"

# ── 4. Load launchd agent ────────────────────────────────────────
# Unload first if already loaded
launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load -w "$PLIST_DEST"
echo "  ✓ launchd agent loaded (auto-starts at login)"

# ── 5. Start it now (don't wait for reboot) ──────────────────────
echo "  → Starting launcher now…"
sleep 2

# Check if it came up
if curl -s --max-time 3 http://localhost:8768/health | grep -q "online"; then
  echo -e "  ${GREEN}✓ EVA Launcher is ONLINE at :8768${RESET}"
else
  echo "  → Not up yet — starting manually…"
  python3 "$LAUNCHER_DIR/eva_launcher.py" &
  sleep 2
  if curl -s --max-time 3 http://localhost:8768/health | grep -q "online"; then
    echo -e "  ${GREEN}✓ EVA Launcher is ONLINE at :8768${RESET}"
  else
    echo "  ⚠ Launcher not responding — check logs at $LOG_DIR/launcher.log"
  fi
fi

echo ""
echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${CYAN}${BOLD}  EVA LAUNCHER READY${RESET}"
echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo "  Health:   http://localhost:8768/health"
echo "  Status:   http://localhost:8768/status"
echo "  Start all: curl -X POST http://localhost:8768/start"
echo ""
echo "  Command Center button now controls all services."
echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
