#!/bin/bash
# Removes all EVA launchd services
LAUNCHD_DIR="$HOME/Library/LaunchAgents"
SERVICES=(com.eva.logger com.eva.context-api com.eva.deal-scout com.eva.content-engine com.eva.screenpipe-watchdog)

echo "Unloading EVA services..."
for svc in "${SERVICES[@]}"; do
    plist="$LAUNCHD_DIR/$svc.plist"
    launchctl unload "$plist" 2>/dev/null && echo "  ✓ $svc unloaded" || echo "  - $svc not loaded"
    rm -f "$plist" && echo "  ✓ $svc plist removed"
done
pkill -x screenpipe 2>/dev/null || true
echo "Done. EVA services removed."
