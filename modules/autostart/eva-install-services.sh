#!/bin/bash
# ─────────────────────────────────────────────────────────────────
#  EVA Services Installer v2
#  Run once after cloning:
#    bash ~/Eva/modules/autostart/eva-install-services.sh
#  Safe to re-run — fully idempotent.
# ─────────────────────────────────────────────────────────────────

set -e

EVA_HOME="$HOME/Eva"
LAUNCHD_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$EVA_HOME/logs"
PLIST_SRC="$EVA_HOME/modules/autostart/launchd"
RUNNER="$EVA_HOME/modules/autostart/run-service.sh"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  EVA SERVICES INSTALLER v2${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ── 1. Create directories ────────────────────────────────────────
echo -e "${YELLOW}[1/5] Creating directories...${NC}"
mkdir -p "$LOG_DIR"
mkdir -p "$LAUNCHD_DIR"
chmod +x "$RUNNER"
echo -e "${GREEN}  ✓ $LOG_DIR${NC}"
echo -e "${GREEN}  ✓ run-service.sh is executable${NC}"

# ── 2. Install Python deps ───────────────────────────────────────
echo -e "${YELLOW}[2/5] Installing Python dependencies...${NC}"

# Source shell env to get the right Python
for rc in "$HOME/.zshrc" "$HOME/.bash_profile" "$HOME/.bashrc" "$HOME/.profile"; do
    [ -f "$rc" ] && source "$rc" 2>/dev/null && break
done

PYTHON=$(which python3 2>/dev/null || echo "/usr/bin/python3")
echo "  Using Python: $PYTHON ($($PYTHON --version 2>&1))"

for module in logger deal-scout content-engine launcher; do
    REQ="$EVA_HOME/modules/$module/requirements.txt"
    if [ -f "$REQ" ]; then
        echo "  → $module..."
        "$PYTHON" -m pip install -r "$REQ" -q
        echo -e "${GREEN}  ✓ $module${NC}"
    else
        echo "  ⚠ No requirements.txt for $module — skipping"
    fi
done

# ── 3. Substitute actual username into plists ────────────────────
echo -e "${YELLOW}[3/5] Configuring plists for user: $USER (home: $HOME)...${NC}"

for plist in "$PLIST_SRC"/*.plist; do
    filename=$(basename "$plist")
    dest="$LAUNCHD_DIR/$filename"
    # Replace hardcoded /Users/vineetkumar with actual home
    sed "s|/Users/vineetkumar|$HOME|g" "$plist" > "$dest"
    echo -e "${GREEN}  ✓ $filename${NC}"
done

# ── 4. Unload + reload services ─────────────────────────────────
echo -e "${YELLOW}[4/5] Loading services into launchd...${NC}"

SERVICES=(
    "com.eva.launcher"
    "com.eva.logger"
    "com.eva.context-api"
    "com.eva.deal-scout"
    "com.eva.content-engine"
)

for svc in "${SERVICES[@]}"; do
    plist="$LAUNCHD_DIR/$svc.plist"
    if [ -f "$plist" ]; then
        # Unload silently if already loaded
        launchctl unload "$plist" 2>/dev/null || true
        sleep 0.3
        launchctl load "$plist"
        echo -e "${GREEN}  ✓ $svc${NC}"
    else
        echo -e "${RED}  ✗ $plist not found${NC}"
    fi
done

# ── 5. Verify ────────────────────────────────────────────────────
echo -e "${YELLOW}[5/5] Waiting 8s then verifying...${NC}"
sleep 8

echo ""
for svc in "${SERVICES[@]}"; do
    pid=$(launchctl list | grep "$svc" | awk '{print $1}')
    if [[ "$pid" =~ ^[0-9]+$ ]]; then
        echo -e "${GREEN}  ✓ $svc (pid $pid)${NC}"
    else
        echo -e "${RED}  ✗ $svc not running — check: tail -20 $LOG_DIR/${svc#com.eva.}.error.log${NC}"
    fi
done

# Port health check
echo ""
echo "  Port check:"
for port in 8765 8766 8767 8768; do
    if nc -z localhost $port 2>/dev/null; then
        echo -e "${GREEN}  ✓ :$port open${NC}"
    else
        echo -e "${RED}  ✗ :$port not responding yet${NC}"
    fi
done

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Done. Services start automatically on login.${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Debug logs:"
echo "    tail -f ~/Eva/logs/eva-content-engine.error.log"
echo "    tail -f ~/Eva/logs/eva-deal-scout.error.log"
echo "    tail -f ~/Eva/logs/eva-context-api.error.log"
echo ""
echo "  Manual status check:"
echo "    launchctl list | grep eva"
echo ""
