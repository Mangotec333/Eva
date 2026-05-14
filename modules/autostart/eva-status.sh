#!/bin/bash
# EVA Services Status Check
CYAN='\033[0;36m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  EVA SYSTEM STATUS${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

check_service() {
    local name=$1
    local label=$2
    local port=$3
    pid=$(launchctl list | grep "$label" | awk '{print $1}')
    if [ -n "$pid" ] && [ "$pid" != "-" ]; then
        if [ -n "$port" ]; then
            if curl -s --max-time 1 "http://localhost:$port/health" > /dev/null 2>&1; then
                echo -e "  ${GREEN}● $name${NC} (pid $pid, port $port responding)"
            else
                echo -e "  ${GREEN}● $name${NC} (pid $pid, port $port starting...)"
            fi
        else
            echo -e "  ${GREEN}● $name${NC} (pid $pid)"
        fi
    else
        echo -e "  ${RED}○ $name${NC} (not running)"
    fi
}

check_service "EVA Logger"          "com.eva.logger"              ""
check_service "Context API"         "com.eva.context-api"         "8765"
check_service "Deal Scout"          "com.eva.deal-scout"          "8766"
check_service "Content Engine"      "com.eva.content-engine"      "8767"
check_service "Screenpipe Watchdog" "com.eva.screenpipe-watchdog" ""

echo ""
SCREENPIPE_PID=$(pgrep -x screenpipe 2>/dev/null || true)
if [ -n "$SCREENPIPE_PID" ]; then
    echo -e "  ${GREEN}● Screenpipe${NC} (pid $SCREENPIPE_PID — active session)"
else
    echo -e "  ○ Screenpipe (paused — watchdog will start on work activity)"
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo "  Logs: ~/Eva/logs/"
echo "  Manage: launchctl list | grep eva"
echo ""
