#!/usr/bin/env bash
# ============================================================
# EVA Voice Module — Autostart Entry
# Append this block to ~/Eva/modules/autostart/eva-install-services.sh
# ============================================================

# ----- Voice Module (port 8774) -----

VOICE_DIR="$HOME/Eva/modules/voice"
VOICE_VENV="$VOICE_DIR/venv"
VOICE_LOG="$VOICE_DIR/voice.log"
VOICE_PLIST="$HOME/Library/LaunchAgents/ai.mangotec.eva.voice.plist"

# Create virtualenv if not present
if [ ! -d "$VOICE_VENV" ]; then
  echo "[EVA] Creating voice module virtualenv..."
  python3 -m venv "$VOICE_VENV"
  "$VOICE_VENV/bin/pip" install -q --upgrade pip
  "$VOICE_VENV/bin/pip" install -q -r "$VOICE_DIR/requirements.txt"
fi

# Write LaunchAgent plist
cat > "$VOICE_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>ai.mangotec.eva.voice</string>

  <key>ProgramArguments</key>
  <array>
    <string>$VOICE_VENV/bin/python</string>
    <string>$VOICE_DIR/voice_service.py</string>
  </array>

  <key>WorkingDirectory</key>
  <string>$VOICE_DIR</string>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONUNBUFFERED</key>
    <string>1</string>
    <key>ANTHROPIC_API_KEY</key>
    <string>YOUR_ANTHROPIC_KEY_HERE</string>
  </dict>

  <key>RunAtLoad</key>
  <true/>

  <key>KeepAlive</key>
  <true/>

  <key>StandardOutPath</key>
  <string>$VOICE_LOG</string>

  <key>StandardErrorPath</key>
  <string>$VOICE_LOG</string>

  <key>ThrottleInterval</key>
  <integer>10</integer>
</dict>
</plist>
PLIST

# Load (or reload) the agent
launchctl unload "$VOICE_PLIST" 2>/dev/null || true
launchctl load -w "$VOICE_PLIST"
echo "[EVA] Voice module LaunchAgent loaded → port 8774"
# ============================================================
