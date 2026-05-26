# EVA Pathfinder — Monetization Funnel Agent

**Port:** `8773`  
**DB:** `~/.eva/pathfinder.db` (SQLite, auto-created on first run)

Pathfinder is EVA's lead scoring and outreach routing engine. It ingests waitlist form submissions, scores each contact as hot/warm/cold, routes them to the right DM sequence, and surfaces follow-up priorities for the EVA Command Center.

---

## Architecture

```
pathfinder_api.py        FastAPI app (port 8773) — all HTTP endpoints
pathfinder_db.py         SQLite layer — schema, queries, DB path (~/.eva/pathfinder.db)
outreach_sequences.py    DM templates (1–10) + sequence cadence definitions
```

### Lead Stages

```
new → contacted → replied → meeting_booked → closed → archived
```

### Scoring Logic

| Tier        | Base Score | Sequence    |
|-------------|-----------|-------------|
| `enterprise`| 90        | `high-touch`|
| `operator`  | 70        | `standard`  |
| `starter`   | 40        | `nurture`   |
| `unsure`    | 50        | `discovery` |

**Pain point bonus:** +15 if the `usecase` field contains any of: `deal`, `acquisition`, `pipeline`, `search`, `acquire`, `sourcing`, `off-market`, `diligence`, `target`, `seller`. Score caps at 100.

### Outreach Sequences

| Sequence     | First DM | Cadence                                      |
|--------------|----------|----------------------------------------------|
| `high-touch` | DM 1     | DM 1 same day → DM 2 day 3 → call day 7     |
| `standard`   | DM 3     | DM 3 day 1 → DM 7 day 5                     |
| `discovery`  | DM 5     | DM 5 day 1                                  |
| `nurture`    | DM 10    | DM 10 day 2                                 |

---

## Setup

### 1. Install dependencies

```bash
pip install fastapi uvicorn pydantic[email]
```

Or add to your environment from the repo root:

```bash
pip install -r modules/pathfinder/requirements.txt
```

### 2. Run the server

```bash
cd modules/pathfinder
python pathfinder_api.py
```

Or with uvicorn directly:

```bash
uvicorn pathfinder_api:app --host 0.0.0.0 --port 8773 --reload
```

### 3. Verify it's running

```bash
curl http://localhost:8773/health
```

Expected response:
```json
{
  "status": "ok",
  "service": "EVA Pathfinder",
  "port": 8773,
  "db": "/Users/<you>/.eva/pathfinder.db",
  "timestamp": "2025-..."
}
```

---

## API Reference

### `POST /pathfinder/lead`

Ingest a waitlist submission. Scores the lead, picks a sequence, saves to DB.

**Request body:**
```json
{
  "name": "Jane Smith",
  "email": "jane@acme.com",
  "company": "Acme Corp",
  "tier": "enterprise",
  "usecase": "We need help with deal sourcing and acquisition pipeline"
}
```

**Response:**
```json
{
  "id": 1,
  "score": 100,
  "sequence": "high-touch",
  "next_action": "DM 1 same day — use DM template #1",
  "first_dm": 1,
  "stage": "new"
}
```

**Tier values:** `enterprise` | `operator` | `starter` | `unsure`

---

### `GET /pathfinder/leads`

Returns all leads ordered by score, plus a follow-up-today count for the Command Center.

**Response:**
```json
{
  "total": 12,
  "follow_up_today": 3,
  "leads": [
    {
      "id": 1,
      "name": "Jane Smith",
      "email": "jane@acme.com",
      "company": "Acme Corp",
      "tier": "enterprise",
      "usecase": "...",
      "score": 100,
      "sequence": "high-touch",
      "stage": "contacted",
      "created_at": "2025-06-01T...",
      "last_contact": "2025-06-01T...",
      "notes": null
    }
  ]
}
```

---

### `POST /pathfinder/lead/{id}/advance`

Advance a lead to the next pipeline stage. Updates `last_contact` timestamp.

**Response:**
```json
{
  "id": 1,
  "previous_stage": "new",
  "current_stage": "contacted",
  "last_contact": "2025-06-01T..."
}
```

Returns `400` if lead is already archived, `404` if ID not found.

---

### `GET /health`

Health check — returns service status and DB path.

---

## EVA Command Center Integration

The Command Center surfaces `follow_up_today` count from `GET /pathfinder/leads`.

Recommended widget data shape:
```json
{
  "module": "pathfinder",
  "endpoint": "http://localhost:8773/pathfinder/leads",
  "highlight_field": "follow_up_today",
  "label": "Follow up today"
}
```

---

## DM Templates

All 10 DM templates live in `outreach_sequences.py` as the `DM_TEMPLATES` dict.  
Source: `linkedin_dealscout_dms.md` — Vineet Ravi / Storeys.  
Templates are EQ-led, curiosity-first LinkedIn DMs targeting ETA searchers — no pitch, no CTA.

| # | Angle |
|---|-------|
| 1 | The Loneliness Angle |
| 2 | The Intuition Angle |
| 3 | The Identity Angle |
| 4 | The Collaboration Angle |
| 5 | The Seller Psychology Angle |
| 6 | The Off-Market Angle |
| 7 | The Search Fatigue Angle |
| 8 | The Criteria Angle |
| 9 | The Operator vs. Acquirer Angle |
| 10 | The Why Angle |

---

## launchd (macOS autostart)

To run Pathfinder as a background service, create a plist at  
`~/Library/LaunchAgents/com.eva.pathfinder.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.eva.pathfinder</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/path/to/eva-repo/modules/pathfinder/pathfinder_api.py</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/Users/USER/.eva/logs/pathfinder.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/USER/.eva/logs/pathfinder_err.log</string>
</dict>
</plist>
```

Load with: `launchctl load ~/Library/LaunchAgents/com.eva.pathfinder.plist`
