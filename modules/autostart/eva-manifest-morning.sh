#!/bin/bash
# ─────────────────────────────────────────────────────────────────
#  EVA Manifestation Loop — Morning Trigger
#  Fires daily at 4:00 AM via com.eva.manifest-morning.plist
#  (launchd StartCalendarInterval, not a persistent service).
#
#  Plays the manifestation video (epic-hype narration + high-energy
#  score, present-tense affirmations for goals already "achieved
#  6 months ago") as part of the 4am wake routine.
#
#  v1 — AI voice + AI-generated silhouette/symbolic visuals.
#  Backlog v2 — swap in cloned own-voice narration + own photos
#  (see EVA_DEVELOPMENT_BACKLOG.md, "EVA Manifestation Loop").
# ─────────────────────────────────────────────────────────────────

EVA_HOME="$HOME/Eva"
VIDEO_PATH="$EVA_HOME/eva-assets/manifestation/EVA_Manifestation_Loop.mp4"
LOG_DIR="$EVA_HOME/logs"
LOG_FILE="$LOG_DIR/manifest-morning.log"

mkdir -p "$LOG_DIR"

if [ ! -f "$VIDEO_PATH" ]; then
    echo "$(date): ERROR — video not found at $VIDEO_PATH" >> "$LOG_FILE"
    exit 1
fi

osascript <<EOF
tell application "QuickTime Player"
    activate
    set theMovie to open POSIX file "$VIDEO_PATH"
    set looping of theMovie to true
    set audio volume of theMovie to 100
    play theMovie
end tell
EOF

echo "$(date): Manifestation Loop triggered ($VIDEO_PATH)" >> "$LOG_FILE"
