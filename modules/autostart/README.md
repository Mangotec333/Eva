# EVA Auto-Start System

This module registers all EVA background services as macOS launchd agents so they start automatically on login and restart if they crash.

---

## One-Time Install

```bash
bash ~/Eva/modules/autostart/eva-install-services.sh
```

The installer:
1. Creates `~/Eva/logs/`
2. Installs Python dependencies from each module's `requirements.txt`
3. Copies and configures plists into `~/Library/LaunchAgents/` (substitutes your actual username and `python3` path)
4. Loads all services via `launchctl`
5. Verifies each service is running

Safe to re-run — fully idempotent.

---

## Services

| Service | Label | Port | Description |
|---|---|---|---|
| EVA Logger | `com.eva.logger` | — | Continuous activity and event logger |
| Context API | `com.eva.context-api` | 8765 | HTTP API serving EVA's current context |
| Deal Scout | `com.eva.deal-scout` | 8766 | Monitors and surfaces deal opportunities |
| Content Engine | `com.eva.content-engine` | 8767 | Content generation and scheduling engine |
| Screenpipe Watchdog | `com.eva.screenpipe-watchdog` | — | Starts/pauses Screenpipe based on activity |

All services use `KeepAlive = true` and `ProcessType = Background`.

---

## Screenpipe Watchdog

Polls every **30 seconds**. Decides whether Screenpipe should run based on:

### Work Apps — always record
> Cursor, Code, Visual Studio Code, Terminal, iTerm2, iTerm, Google Chrome, Safari, Firefox, Arc, Notion, Obsidian, Notes, Slack, Mail, Zoom, Microsoft Teams, Perplexity, Claude, Xcode, PyCharm, WebStorm, Finder

### Research Apps — record only if a work app was active in the last 30 min
> YouTube (URL-based detection via Chrome)

### Pause Apps — always stop recording
> Netflix, Spotify, VLC, QuickTime Player, App Store, System Preferences, System Settings, Photos, FaceTime, Music, Podcasts, TV, Apple TV

### Idle Threshold
> **10 minutes** of keyboard/mouse inactivity → pause Screenpipe

### Decision Logic

1. Idle > 10 min → **pause**
2. Active app in Pause Apps → **pause**
3. Active app in Work Apps → **run** (resets 30-min work session timer)
4. Active app in Research Apps + work session active → **run**
5. Unknown app → **maintain current state**

To add a work app, edit the `WORK_APPS` set in `~/Eva/modules/autostart/eva-screenpipe-watchdog.py`.

---

## Status Check

```bash
bash ~/Eva/modules/autostart/eva-status.sh
```

Shows each service's PID, port health, and whether Screenpipe is currently running.

Alternatively:

```bash
launchctl list | grep eva
```

---

## Uninstall

```bash
bash ~/Eva/modules/autostart/eva-uninstall-services.sh
```

Unloads and removes all EVA plist files from `~/Library/LaunchAgents/`. Also kills any running Screenpipe process.

---

## Logs

All logs are written to `~/Eva/logs/`:

| File | Description |
|---|---|
| `eva-logger.log` | EVA Logger stdout |
| `eva-logger.error.log` | EVA Logger stderr |
| `eva-context-api.log` | Context API stdout |
| `eva-context-api.error.log` | Context API stderr |
| `eva-deal-scout.log` | Deal Scout stdout |
| `eva-deal-scout.error.log` | Deal Scout stderr |
| `eva-content-engine.log` | Content Engine stdout |
| `eva-content-engine.error.log` | Content Engine stderr |
| `eva-screenpipe-watchdog.log` | Watchdog decisions and state changes |
| `eva-screenpipe-watchdog.error.log` | Watchdog stderr |
| `screenpipe.log` | Screenpipe process output |

---

## File Structure

```
~/Eva/modules/autostart/
├── eva-screenpipe-watchdog.py   # Screenpipe control daemon
├── eva-install-services.sh      # One-time installer
├── eva-uninstall-services.sh    # Clean uninstaller
├── eva-status.sh                # Quick status check
├── README.md                    # This file
└── launchd/
    ├── com.eva.logger.plist
    ├── com.eva.context-api.plist
    ├── com.eva.deal-scout.plist
    ├── com.eva.content-engine.plist
    └── com.eva.screenpipe-watchdog.plist
```

---

## Manual Service Management

```bash
# Stop a single service
launchctl unload ~/Library/LaunchAgents/com.eva.<name>.plist

# Start a single service
launchctl load ~/Library/LaunchAgents/com.eva.<name>.plist

# Restart a service
launchctl unload ~/Library/LaunchAgents/com.eva.<name>.plist
launchctl load ~/Library/LaunchAgents/com.eva.<name>.plist
```
