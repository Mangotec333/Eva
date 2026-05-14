#!/bin/bash
# EVA Services Installer
# Run once after cloning: bash ~/Eva/modules/autostart/eva-install-services.sh
# Safe to re-run — idempotent

set -e

EVA_HOME="$HOME/Eva"
LAUNCHD_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$EVA_HOME/logs"
PLIST_SRC="$EVA_HOME/modules/autostart/launchd"
PYTHON=$(which python3)

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  EVA SERVICES INSTALLER${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# 1. Create log directory
echo -e "${YELLOW}[1/5] Creating log directory...${NC}"
mkdir -p "$LOG_DIR"
echo -e "${GREEN}  ✓ $LOG_DIR${NC}"

# 2. Install Python dependencies for each module
echo -e "${YELLOW}[2/5] Installing Python dependencies...${NC}"
for module in logger deal-scout content-engine; do
    REQ="$EVA_HOME/modules/$module/requirements.txt"
    if [ -f "$REQ" ]; then
        echo "  Installing $module deps..."
        $PYTHON -m pip install -r "$REQ" -q
        echo -e "${GREEN}  ✓ $module${NC}"
    fi
done

# 3. Substitute actual username into plist files
echo -e "${YELLOW}[3/5] Configuring launchd plists for user: $USER...${NC}"
ACTUAL_HOME="$HOME"
for plist in "$PLIST_SRC"/*.plist; do
    filename=$(basename "$plist")
    dest="$LAUNCHD_DIR/$filename"
    # Replace placeholder username with actual
    sed "s|/Users/vineetkumar|$ACTUAL_HOME|g" "$plist" > "$dest"
    # Replace /usr/bin/python3 with actual python3 path
    sed -i "s|/usr/bin/python3|$PYTHON|g" "$dest"
    echo -e "${GREEN}  ✓ $filename → $LAUNCHD_DIR${NC}"
done

# 4. Load all services into launchd
echo -e "${YELLOW}[4/5] Loading services into launchd...${NC}"
SERVICES=(
    "com.eva.logger"
    "com.eva.context-api"
    "com.eva.deal-scout"
    "com.eva.content-engine"
    "com.eva.screenpipe-watchdog"
)
for svc in "${SERVICES[@]}"; do
    plist="$LAUNCHD_DIR/$svc.plist"
    if [ -f "$plist" ]; then
        # Unload first if already loaded (idempotent)
        launchctl unload "$plist" 2>/dev/null || true
        launchctl load "$plist"
        echo -e "${GREEN}  ✓ $svc loaded${NC}"
    else
        echo -e "${RED}  ✗ $plist not found — skipping${NC}"
    fi
done

# 5. Verify services are running
echo -e "${YELLOW}[5/5] Verifying services...${NC}"
sleep 3
for svc in "${SERVICES[@]}"; do
    status=$(launchctl list | grep "$svc" | awk '{print $1}')
    if [ -n "$status" ]; then
        echo -e "${GREEN}  ✓ $svc (pid: $status)${NC}"
    else
        echo -e "${YELLOW}  ⚠ $svc not yet running (may still be starting)${NC}"
    fi
done

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  EVA SERVICES INSTALLED${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Services start automatically on login."
echo "  Logs: ~/Eva/logs/"
echo ""
echo "  To check status:    launchctl list | grep eva"
echo "  To stop a service:  launchctl unload ~/Library/LaunchAgents/com.eva.<name>.plist"
echo "  To uninstall all:   bash ~/Eva/modules/autostart/eva-uninstall-services.sh"
echo ""
