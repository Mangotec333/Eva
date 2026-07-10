#!/bin/bash
# ─────────────────────────────────────────────────────────────────
#  EVA Services Status Check
#  Combines three signals into a single up/down/healthy verdict:
#    1. launchd     — is the job loaded and does it have a live PID?
#    2. status file — what did run-service.sh last record?
#       (~/Eva/logs/status/<label>.status: state + reason + timestamp)
#    3. port health — does the service answer on http://localhost:<port>/health?
# ─────────────────────────────────────────────────────────────────
CYAN='\033[0;36m'; GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; DIM='\033[2m'; NC='\033[0m'

EVA_HOME="$HOME/Eva"
STATUS_DIR="$EVA_HOME/logs/status"

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  EVA SYSTEM STATUS${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Read a single key out of a service's status file.
status_field() {
    local label="$1" key="$2" file="$STATUS_DIR/$1.status"
    [ -f "$file" ] || return 0
    grep "^$key=" "$file" 2>/dev/null | head -1 | cut -d= -f2-
}

# label -> launchd PID ("-" or empty when not running)
launchd_pid() {
    launchctl list 2>/dev/null | grep -w "$1" | awk '{print $1}' | head -1
}

port_healthy() {
    curl -s --max-time 1 "http://localhost:$1/health" >/dev/null 2>&1
}

check_service() {
    local name="$1" label="$2" port="$3"
    local pid state reason short
    # run-service.sh keys status files by the short label (com.eva.<x> -> <x>)
    short="${label#com.eva.}"
    pid=$(launchd_pid "$label")
    state=$(status_field "$short" state)
    reason=$(status_field "$short" reason)

    local dot color detail
    if [[ "$pid" =~ ^[0-9]+$ ]]; then
        # Job is alive under launchd. Refine with port + status file.
        if [ -n "$port" ]; then
            if port_healthy "$port"; then
                dot="●"; color=$GREEN; detail="pid $pid, :$port healthy"
            elif [ "$state" = "waiting" ]; then
                dot="◐"; color=$YELLOW; detail="pid $pid, ${reason:-waiting for launcher}"
            else
                dot="◐"; color=$YELLOW; detail="pid $pid, :$port not answering yet"
            fi
        else
            dot="●"; color=$GREEN; detail="pid $pid${state:+, $state}"
        fi
    else
        dot="○"; color=$RED
        if [ -n "$state" ]; then
            detail="not running (last: $state${reason:+ — $reason})"
        else
            detail="not running"
        fi
    fi
    printf "  ${color}%s %-22s${NC} ${DIM}%s${NC}\n" "$dot" "$name" "$detail"
}

#             Display name            launchd label                 port
check_service "EVA Launcher"          "com.eva.launcher"            "8768"
check_service "EVA Logger"            "com.eva.logger"              ""
check_service "Context API"           "com.eva.context-api"         "8765"
check_service "Deal Scout"            "com.eva.deal-scout"          "8766"
check_service "Content Engine"        "com.eva.content-engine"      "8767"
check_service "Channels"              "com.eva.channels"            "8770"
check_service "Knowledge"             "com.eva.knowledge"           "8771"
check_service "Voice (AV input)"      "com.eva.voice"               "8774"
check_service "Monetizing Agent"      "com.eva.monetizing"          "8772"
check_service "State Ledger"          "com.eva.eva-state"           "8769"
check_service "GHL Agent"             "com.eva.ghl-agent"           "8782"
check_service "Screenpipe Watchdog"   "com.eva.screenpipe-watchdog" ""
check_service "Wake Daemon"           "com.eva.wake-daemon"         ""

echo ""
SCREENPIPE_PID=$(pgrep -x screenpipe 2>/dev/null || true)
if [ -n "$SCREENPIPE_PID" ]; then
    echo -e "  ${GREEN}● Screenpipe${NC} ${DIM}(pid $SCREENPIPE_PID — active capture session)${NC}"
else
    echo -e "  ${DIM}○ Screenpipe (paused — watchdog starts it on work activity)${NC}"
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo "  Legend:  ● up/healthy   ◐ starting/waiting   ○ down"
echo "  Status files: $STATUS_DIR/<label>.status"
echo "  Logs:         $EVA_HOME/logs/"
echo "  Launcher:     curl -s http://localhost:8768/health"
echo "  Manage:       launchctl list | grep eva"
echo ""
