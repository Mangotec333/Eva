#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  EVA MORNING STARTUP SCRIPT
#  Launches all EVA services in macOS Terminal tabs.
#  Run once:  bash ~/Eva/eva-start.sh
# ─────────────────────────────────────────────────────────────────

CYAN='\033[0;36m'; BOLD='\033[1m'; GREEN='\033[0;32m'; RED='\033[0;31m'; RESET='\033[0m'

echo -e "${CYAN}${BOLD}"
cat << 'EOF'
  ███████╗██╗   ██╗ █████╗      ██████╗ ███╗   ██╗██╗     ██╗███╗   ██╗███████╗
  ██╔════╝██║   ██║██╔══██╗    ██╔═══██╗████╗  ██║██║     ██║████╗  ██║██╔════╝
  █████╗  ██║   ██║███████║    ██║   ██║██╔██╗ ██║██║     ██║██╔██╗ ██║█████╗
  ██╔══╝  ╚██╗ ██╔╝██╔══██║    ██║   ██║██║╚██╗██║██║     ██║██║╚██╗██║██╔══╝
  ███████╗ ╚████╔╝ ██║  ██║    ╚██████╔╝██║ ╚████║███████╗██║██║ ╚████║███████╗
  ╚══════╝  ╚═══╝  ╚═╝  ╚═╝     ╚═════╝ ╚═╝  ╚═══╝╚══════╝╚═╝╚═╝  ╚═══╝╚══════╝
EOF
echo -e "${RESET}"
echo -e "${CYAN}  Initialising EVA OS — $(date '+%A, %B %-d %Y  %H:%M:%S')${RESET}"
echo ""

# ── Helper: open new Terminal tab ────────────────────────────────
open_tab() {
  local cmd="$1"
  osascript -e "
tell application \"Terminal\"
  activate
  tell application \"System Events\" to keystroke \"t\" using command down
  delay 0.5
  do script \"${cmd}\" in front window
end tell
"
}

# ── Check deps installed ─────────────────────────────────────────
check_dep() {
  python3 -c "import $1" 2>/dev/null
}

echo "  Checking dependencies…"
MISSING=0
for pkg in fastapi uvicorn psutil aiosqlite apscheduler; do
  if ! check_dep "$pkg" 2>/dev/null; then
    echo -e "  ${RED}✗ Missing: $pkg${RESET}"
    MISSING=1
  fi
done

if [ "$MISSING" -eq 1 ]; then
  echo ""
  echo -e "  ${RED}${BOLD}Dependencies missing — installing now…${RESET}"
  bash ~/Eva/eva-install-deps.sh
  echo ""
fi
echo -e "  ${GREEN}✓ Dependencies OK${RESET}"
echo ""

# ── Tab 1: Screenpipe ─────────────────────────────────────────────
echo "  → Tab 1: screenpipe"
open_tab "echo '=== SCREENPIPE ===' && screenpipe || echo 'screenpipe not found — install from https://github.com/mediar-ai/screenpipe'"

# ── Tab 2: EVA Logger ─────────────────────────────────────────────
echo "  → Tab 2: EVA Logger"
open_tab "echo '=== EVA LOGGER ===' && cd ~/Eva/modules/logger && python3 eva_logger.py"

# ── Tab 3: Context API (:8765) ────────────────────────────────────
echo "  → Tab 3: Context API :8765"
open_tab "echo '=== CONTEXT API :8765 ===' && cd ~/Eva/modules/logger && python3 eva_context_api.py"

# ── Tab 4: Deal Scout (:8766) ─────────────────────────────────────
echo "  → Tab 4: Deal Scout :8766"
open_tab "echo '=== DEAL SCOUT :8766 ===' && cd ~/Eva/modules/deal-scout && python3 main.py"

# ── Tab 5: Content Engine (:8767) ─────────────────────────────────
echo "  → Tab 5: Content Engine :8767"
open_tab "echo '=== CONTENT ENGINE :8767 ===' && cd ~/Eva/modules/content-engine && python3 main.py"

# ── Wait and verify ───────────────────────────────────────────────
echo ""
echo "  Waiting 6 seconds for services to initialise…"
sleep 6

echo ""
echo "  Checking service health:"
check_port() {
  local name="$1"; local port="$2"
  if curl -s --max-time 2 "http://localhost:$port/health" | grep -q "online\|ok\|status" 2>/dev/null; then
    echo -e "  ${GREEN}✓ $name :$port${RESET}"
  else
    echo -e "  ${RED}✗ $name :$port — check Terminal tab for errors${RESET}"
  fi
}
check_port "Context API"    8765
check_port "Deal Scout"     8766
check_port "Content Engine" 8767
check_port "Launcher"       8768

# ── Open Command Center ───────────────────────────────────────────
echo ""
echo "  → Opening Command Center…"
open "https://eva.mangotec.ai"

echo ""
echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${CYAN}${BOLD}  EVA SYSTEMS ONLINE${RESET}"
echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo "  Context API    →  http://localhost:8765/health"
echo "  Deal Scout     →  http://localhost:8766/health"
echo "  Content Engine →  http://localhost:8767/health"
echo "  Launcher       →  http://localhost:8768/health"
echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
