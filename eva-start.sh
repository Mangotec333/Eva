#!/usr/bin/env bash
# ─────────────────────────────────────────────
#  EVA MORNING STARTUP SCRIPT
#  Launches all EVA services in macOS Terminal tabs
#  and opens the morning browser dashboards.
# ─────────────────────────────────────────────

# ── Colours ──────────────────────────────────
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ── Banner ────────────────────────────────────
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

# ── Helper: open a new Terminal tab running a command ────────────────────────
open_terminal_tab() {
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

# ── Tab 1: screenpipe ─────────────────────────────────────────────────────────
echo "  → Launching screenpipe (Tab 1)…"
open_terminal_tab "screenpipe"

# ── Tab 2: EVA Logger ────────────────────────────────────────────────────────
echo "  → Launching eva_logger.py (Tab 2)…"
open_terminal_tab "cd ~/Eva/modules/logger && python eva_logger.py"

# ── Tab 3: Context API ───────────────────────────────────────────────────────
echo "  → Launching eva_context_api.py (Tab 3)…"
open_terminal_tab "cd ~/Eva/modules/logger && python eva_context_api.py"

# ── Tab 4: Deal Scout ────────────────────────────────────────────────────────
echo "  → Launching deal-scout/main.py (Tab 4)…"
open_terminal_tab "cd ~/Eva/modules/deal-scout && python main.py"

# ── Wait for services to initialise ─────────────────────────────────────────
echo ""
echo "  Waiting 4 seconds for services to initialise…"
sleep 4

# ── Open browser dashboards ──────────────────────────────────────────────────
echo "  → Opening Morning OS in browser…"
open "https://www.perplexity.ai/computer/a/eva-morning-os-3Tmx6H6.SsOgfEUZegsOJw"

echo "  → Opening Command Center in browser…"
open "https://www.perplexity.ai/computer/a/eva-command-center-9qREfmTGTtGonVZQWBJ_xg"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${CYAN}${BOLD}  EVA SYSTEMS ONLINE${RESET}"
echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo "  Screenpipe     →  localhost:3030"
echo "  Context API    →  localhost:8765/health"
echo "  Deal Scout     →  localhost:8766/health"
echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo "  Morning OS     →  opening in browser"
echo "  Command Center →  opening in browser"
echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
