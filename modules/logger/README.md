# EVA Activity Logger

**Module 1 of EVA's architecture.** A lightweight background daemon that tracks your computer activity — active apps, focus blocks, context switches, and idle time — so EVA can learn your work patterns over time.

---

## What Gets Tracked

| Signal | Detail |
|---|---|
| Active app + window title | Polled every 10 seconds |
| Time per application | Aggregated per session and per day |
| Context switches | Every time you change apps |
| Idle detection | No input for 5+ minutes |
| Work sessions | Contiguous focus blocks |
| Session start/end | Daemon lifetime |

---

## Files

```
eva-logger/
├── eva_logger.py                 # Core daemon — runs in background
├── eva_context_api.py            # FastAPI server — serves data to EVA
├── eva_summarize.py              # Daily summary generator
├── eva_activitywatch_bridge.py   # ActivityWatch integration + fallback
├── requirements.txt              # Python dependencies
├── setup.sh                      # One-time setup script
└── README.md                     # This file
```

**Data written to:**
```
~/eva-data/
├── activity/
│   ├── 2026-05-14.jsonl   # Raw events (JSON Lines, one per line)
│   └── 2026-05-15.jsonl
└── summaries/
    ├── 2026-05-14.json    # End-of-day aggregated summary
    └── 2026-05-15.json
```

---

## Installation

### 1. Install dependencies

```bash
cd eva-logger
bash setup.sh
```

Or manually:

```bash
pip install fastapi "uvicorn[standard]" psutil python-dateutil
```

**Platform extras:**
- **macOS**: nothing extra needed — uses built-in `osascript`
- **Linux**: `sudo apt install xdotool` (enables window tracking)
- **Windows**: `pip install pywin32` (enables native window tracking)

### 2. Verify Python 3.9+

```bash
python3 --version
```

---

## Running the Logger

### Test mode (recommended first step)

Runs for 60 seconds, prints everything captured, then exits:

```bash
python eva_logger.py --test
```

Switch a few apps during the 60 seconds to generate data. You'll see output like:

```
════════════════════════════════════════════════════════════
  EVA LOGGER — TEST MODE (60 seconds)
════════════════════════════════════════════════════════════
Capturing activity...

  [08:01:00] window_focus          | cursor               | eva_logger.py - EVA Project
  [08:01:10] window_focus          | chrome               | GitHub - EVA
  ...

App time (seconds):
  cursor                    42.3s
  chrome                    17.1s

Context switches : 3
Log file         : ~/eva-data/activity/2026-05-14.jsonl
```

### Run as daemon (background)

```bash
# Run in background (macOS/Linux)
nohup python eva_logger.py > ~/eva-data/eva_logger.log 2>&1 &
echo $! > ~/eva-data/eva_logger.pid

# Foreground (shows live log output)
python eva_logger.py
```

**Stop the daemon:**
```bash
kill $(cat ~/eva-data/eva_logger.pid)
```

---

## Running the Context API

The API server makes EVA's data available over HTTP on port **8765**.

```bash
python eva_context_api.py
```

Or with auto-reload during development:
```bash
uvicorn eva_context_api:app --port 8765 --reload
```

### Verify it's working

```bash
curl http://localhost:8765/health
```

Expected response:
```json
{
  "status": "ok",
  "service": "EVA Context API",
  "version": "1.0.0",
  "timestamp": "2026-05-14T08:30:00"
}
```

**All endpoints:**

| Endpoint | Description |
|---|---|
| `GET /health` | Health check |
| `GET /context/today` | Today's full summary |
| `GET /context/week` | This week's breakdown |
| `GET /context/patterns` | 30-day patterns (peak hours, top apps) |
| `GET /context/recent?minutes=60` | Last N minutes of activity |

---

## Generating a Daily Summary

Run on demand or schedule via cron:

```bash
# Today's summary
python eva_summarize.py

# Specific date
python eva_summarize.py --date 2026-05-14

# Print only (don't save)
python eva_summarize.py --print
```

**Example output:**
```
════════════════════════════════════════════════════════════
  EVA DAILY SUMMARY — 2026-05-14
════════════════════════════════════════════════════════════

  Total active time  : 347.2 minutes
  Focus score        : 71 / 100
  Context switches   : 38
  Idle periods       : 2
  Peak focus hour    : 09:00
  Longest block      : 87.3 min (cursor)

  ────────────────────────────────────────────────────────
  TIME BY CATEGORY
  ────────────────────────────────────────────────────────
  coding            187.4 min  ████████████████████████
  browsing           82.1 min  ██████████
  communication      61.5 min  ████████
  productivity       16.2 min  ██

  ────────────────────────────────────────────────────────
  EVA INSIGHT
  ────────────────────────────────────────────────────────
  A moderate focus day (score 71/100): best block was
  08:15–09:42 (87.3 min in cursor); 38 context switches,
  most time in coding (cursor).
```

**Saved to:** `~/eva-data/summaries/2026-05-14.json`

### Schedule with cron (auto-summarize at 11 PM)

```bash
crontab -e
# Add:
0 23 * * * cd /path/to/eva-logger && python eva_summarize.py >> ~/eva-data/summaries.log 2>&1
```

---

## What the Data Looks Like

### Raw activity log (`~/eva-data/activity/2026-05-14.jsonl`)

One JSON object per line:

```json
{"timestamp": "2026-05-14T08:00:01", "event_type": "session_start", "app_name": "", "window_title": "", "duration_seconds": 0, "session_id": "a1b2c3d4-..."}
{"timestamp": "2026-05-14T08:00:11", "event_type": "window_focus", "app_name": "cursor", "window_title": "eva_logger.py - EVA Project", "duration_seconds": 10.0, "session_id": "a1b2c3d4-..."}
{"timestamp": "2026-05-14T08:05:32", "event_type": "window_focus", "app_name": "chrome", "window_title": "FastAPI Docs", "duration_seconds": 321.0, "session_id": "a1b2c3d4-..."}
{"timestamp": "2026-05-14T08:15:00", "event_type": "idle_start", "app_name": "chrome", "window_title": "", "duration_seconds": 580.1, "session_id": "a1b2c3d4-..."}
{"timestamp": "2026-05-14T08:24:12", "event_type": "idle_end", "app_name": "", "window_title": "", "duration_seconds": 0, "session_id": "a1b2c3d4-..."}
```

**Event types:**

| Type | Meaning |
|---|---|
| `session_start` | Logger daemon started |
| `session_end` | Logger daemon stopped |
| `window_focus` | User focused on app for `duration_seconds` |
| `idle_start` | No input for 5+ minutes |
| `idle_end` | User returned from idle |

### Summary (`~/eva-data/summaries/2026-05-14.json`)

```json
{
  "date": "2026-05-14",
  "total_active_minutes": 347.2,
  "focus_score": 71,
  "top_apps": [
    {"app": "cursor", "minutes": 187.4, "percentage": 53.9},
    {"app": "chrome", "minutes": 82.1, "percentage": 23.6}
  ],
  "top_category": "coding",
  "category_breakdown": {
    "coding": 187.4,
    "browsing": 82.1,
    "communication": 61.5,
    "productivity": 16.2,
    "other": 0
  },
  "work_sessions": [
    {"start": "08:15", "end": "09:42", "duration_minutes": 87.3, "primary_app": "cursor"},
    {"start": "10:00", "end": "12:30", "duration_minutes": 150.0, "primary_app": "cursor"}
  ],
  "context_switches": 38,
  "idle_periods": 2,
  "longest_focus_block_minutes": 87.3,
  "longest_focus_block_app": "cursor",
  "peak_focus_hour": "09:00",
  "eva_insight": "A moderate focus day (score 71/100): best block was 08:15–09:42..."
}
```

---

## ActivityWatch Integration (Recommended)

[ActivityWatch](https://activitywatch.net) is a free, open-source, privacy-first app tracker that runs entirely on your machine. When it's running, EVA automatically uses it as the **preferred data source** — giving you richer, more complete activity data with zero extra effort.

### Why ActivityWatch?

| | Built-in `eva_logger` | ActivityWatch |
|---|---|---|
| App + window tracking | Yes | Yes |
| Browser tab titles | No | Yes (via extension) |
| Always-on (survives reboots) | Requires setup | Yes (system tray) |
| Historical data | From first run | From install date |
| Privacy | 100% local | 100% local |

### Install ActivityWatch

1. Download from **https://activitywatch.net** (macOS, Windows, Linux — all free)
2. Run the installer and launch ActivityWatch — it appears in your system tray
3. It starts tracking immediately; data lives at `~/.local/share/activitywatch/`

### Install the browser extension (strongly recommended)

Without the extension, ActivityWatch only sees *which browser* is open, not *which tab*. The extension adds full URL + title tracking:

- **Chrome / Arc / Brave**: [aw-watcher-web on Chrome Web Store](https://chrome.google.com/webstore/detail/activitywatch-web-watcher/nglaklhklhcoonedhgnpgddginnjdadi)
- **Firefox**: [aw-watcher-web on Firefox Add-ons](https://addons.mozilla.org/en-US/firefox/addon/aw-watcher-web/)

### How EVA uses ActivityWatch

The `eva_activitywatch_bridge.py` module is EVA's unified data layer:

```
eva_context_api.py
        │
        ▼
eva_activitywatch_bridge.py  ──── ActivityWatch running? ──▶ ActivityWatch API
                             │                                  (richer data)
                             └─── Not running? ─────────────▶ eva_logger JSONL
                                                               (built-in fallback)
```

- **ActivityWatch running**: bridge fetches from `http://localhost:5600`, normalises all window + browser bucket events into EVA's canonical format
- **ActivityWatch not running**: bridge transparently falls back to EVA's own `~/eva-data/activity/` logs — no config change needed

EVA prefers ActivityWatch data when available but **never requires it**.

### Check which source is active

```bash
python eva_activitywatch_bridge.py
```

Example output:
```
══════════════════════════════════════════════════════════════
  EVA ACTIVITYWATCH BRIDGE — 2026-05-14
══════════════════════════════════════════════════════════════

  ActivityWatch running   : ✓  (http://localhost:5600/api/0)
  Active data source      : ACTIVITYWATCH
  AW buckets found        : 3
    • aw-watcher-window_hostname
    • aw-watcher-afk_hostname
    • aw-watcher-web-chrome_hostname
  eva_logger files        : 5 day(s) on disk
  Today's events          : 312
  Today's active minutes  : 347.2
```

If ActivityWatch is not installed:
```
  ActivityWatch running   : ✗  (http://localhost:5600/api/0)
  Active data source      : EVA_LOGGER
```

### Use from Python

Other EVA modules should import the bridge instead of reading files directly:

```python
from eva_activitywatch_bridge import ActivityWatchBridge

bridge  = ActivityWatchBridge()
print(bridge.source)                          # "activitywatch" or "eva_logger"
events  = bridge.get_events(date.today())     # canonical EVA events
summary = bridge.get_today_summary()          # aggregated summary dict
```

### Canonical EVA event format

All events — regardless of source — are normalised to this shape:

```json
{
  "eva_timestamp":    "2026-05-14T08:23:11",
  "source":           "activitywatch",
  "layer":            "behavior",
  "app":              "Cursor",
  "window":           "eva_logger.py — EVA Project",
  "category":         "deep_work",
  "duration_seconds": 847,
  "session_id":       "aw-watcher-window_hostname",
  "goals_aligned":    null,
  "eva_context": {
    "scheduled_priority": null,
    "actual_activity":    "Cursor — deep_work",
    "alignment_score":    null
  }
}
```

**Categories:**

| Category | Apps |
|---|---|
| `deep_work` | Cursor, VS Code, Xcode, Terminal, PyCharm, any IDE |
| `browsing` | Chrome, Safari, Firefox, Arc, Brave |
| `communication` | Slack, Gmail, Mail, Zoom, Teams, Discord |
| `other` | Everything else |

---

## How EVA Will Use This Data

This is Module 1. Once data accumulates, EVA agents can:

1. **Answer questions about your work** — "What did I spend most time on yesterday?"
2. **Surface focus patterns** — "You code best 08:00–10:30; schedule deep work then."
3. **Detect anomalies** — "You had 3x more context switches than your average today."
4. **Plan your day** — Know when to suggest focus blocks vs. meetings.
5. **Connect to calendar** — Cross-reference with Google Calendar events to label sessions.
6. **Weekly reviews** — Auto-generate Monday morning briefings about last week.

The API server (`/context/*`) is the interface future EVA modules will call directly. Keep it running alongside the logger daemon.

---

## Troubleshooting

**Logger shows "unknown" for app name**
- macOS: Grant Terminal/your IDE "Accessibility" or "Automation" permissions in System Preferences → Privacy & Security.
- Linux: Install `xdotool`.
- Windows: Install `pywin32`.

**API returns empty data**
- Make sure `eva_logger.py` ran first to generate log files.
- Check `~/eva-data/activity/` for `.jsonl` files.

**High CPU usage**
- Default poll interval is 10 seconds. Increase `POLL_INTERVAL` in `eva_logger.py` if needed.

---

## Privacy

All data is stored **locally** on your machine in `~/eva-data/`. Nothing is sent anywhere unless you explicitly connect EVA to external services.
