#!/bin/bash
# ─────────────────────────────────────────────────────────────────
#  EVA Cold Boot Script
#  Solves the chicken-and-egg: starts Launcher first, then all services.
#
#  Usage (paste in Terminal):
#    bash ~/Eva/modules/autostart/eva-boot.sh
#
#  After this runs once, use the Command Center "Start EVA" button.
# ─────────────────────────────────────────────────────────────────

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
EVA_HOME="$HOME/Eva"
LAUNCHER="$EVA_HOME/modules/launcher/eva_launcher.py"

echo ""
echo -e "${CYAN}  EVA — Cold Boot${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# ── Source shell env ─────────────────────────────────────────────
for rc in "$HOME/.zshrc" "$HOME/.bash_profile" "$HOME/.bashrc" "$HOME/.profile"; do
    [ -f "$rc" ] && source "$rc" 2>/dev/null && break
done

PYTHON=$(which python3 2>/dev/null || echo "/usr/bin/python3")

# ── 1. Kill anything already on :8768 ───────────────────────────
echo -e "${YELLOW}[1] Clearing port :8768...${NC}"
lsof -ti :8768 | xargs kill -9 2>/dev/null || true
sleep 1

# ── 2. Start Launcher in background ─────────────────────────────
echo -e "${YELLOW}[2] Starting EVA Launcher on :8768...${NC}"
nohup "$PYTHON" "$LAUNCHER" > "$EVA_HOME/logs/eva-launcher.log" 2>&1 &
LAUNCHER_PID=$!
echo "    PID: $LAUNCHER_PID"

# ── 3. Wait for launcher to be ready (up to 15s) ────────────────
echo -e "${YELLOW}[3] Waiting for launcher...${NC}"
for i in $(seq 1 15); do
    if curl -s --max-time 1 http://localhost:8768/health | grep -q "online" 2>/dev/null; then
        echo -e "${GREEN}  ✓ Launcher online (:8768)${NC}"
        break
    fi
    printf "    attempt %d/15...\r" $i
    sleep 1
done

# Verify it actually came up
if ! curl -s --max-time 2 http://localhost:8768/health | grep -q "online" 2>/dev/null; then
    echo -e "${RED}  ✗ Launcher failed to start. Check: tail -50 ~/Eva/logs/eva-launcher.log${NC}"
    exit 1
fi

# ── 4. Launch all services via Launcher API ──────────────────────
echo -e "${YELLOW}[4] Starting all EVA services...${NC}"
curl -s -X POST http://localhost:8768/start > /dev/null
sleep 3

# ── 5. Status check ──────────────────────────────────────────────
echo -e "${YELLOW}[5] Status:${NC}"
STATUS=$(curl -s http://localhost:8768/status 2>/dev/null)
if [ -n "$STATUS" ]; then
    ONLINE=$(echo "$STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('online',0))" 2>/dev/null || echo "?")
    TOTAL=$(echo "$STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('total',0))" 2>/dev/null || echo "?")
    echo -e "${GREEN}  ✓ $ONLINE / $TOTAL services online${NC}"
else
    echo "    (status unavailable — check Command Center)"
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  EVA is running. Open eva.mangotec.ai${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
