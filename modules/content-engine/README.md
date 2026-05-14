# EVA Content Engine

Nightly LinkedIn draft generation from the EVA activity stream. Converts raw behavioral data — deals evaluated, patterns flagged, builds shipped — into ready-to-approve LinkedIn posts with zero manual input.

**Port:** `8767`

---

## Endpoints

| Path | Method | Description |
|------|--------|-------------|
| `/health` | GET | Health check |
| `/drafts` | GET | List all drafts (filterable by status/platform) |
| `/drafts/{id}` | GET | Get single draft |
| `/drafts/generate` | POST | Generate drafts from a provided activity summary |
| `/drafts/generate-from-eva` | POST | Pull latest EVA activity and auto-generate drafts |
| `/drafts/{id}/approve` | POST | Approve a draft for posting |
| `/drafts/{id}/reject` | POST | Reject a draft with optional reason |
| `/drafts/{id}/post` | POST | Post an approved draft to LinkedIn immediately |
| `/drafts/{id}/schedule` | POST | Schedule a draft for a future time |
| `/drafts/{id}/performance` | GET | Fetch live performance metrics for a posted draft |
| `/drafts/{id}` | DELETE | Delete a draft |
| `/queue` | GET | View the approved-and-ready posting queue |
| `/queue/next` | POST | Post the next item in the queue |
| `/linkedin/config` | POST | Set LinkedIn access_token and person_urn |
| `/linkedin/config` | GET | View current LinkedIn config (token masked) |
| `/analytics/summary` | GET | Aggregate performance across all posted content |
| `/templates` | GET | List available template families |

---

## Brand Voice System

Three voice modes map to different content types:

| Voice | Key | When to Use |
|-------|-----|-------------|
| `thought_leader` | `llm_intuition`, `deal_flow` | Frameworks, mental models, acquisition analysis — high-reach posts that build authority |
| `builder_log` | `builder_log`, `pattern_interrupt` | Raw build updates, EVA learnings, honest metrics — medium-reach posts that build trust |
| `human_story` | `human_story` | Personal moments, relationship observations, emotional anchors — high-reach posts that build connection |

Each template family has 4 hook variants. Drafts are randomly sampled at generation time to avoid repetition.

---

## Nightly Schedule

| Time | Job |
|------|-----|
| 11:00 PM | `nightly_generate` fires → calls `/drafts/generate-from-eva` → creates 3 new drafts |
| 7:00 AM | Morning OS review surfaces drafts in queue |
| Every 6h | `fetch_performance` updates metrics on posted content |

---

## LinkedIn OAuth Setup

1. Create an app at [LinkedIn Developer Portal](https://www.linkedin.com/developers/apps)
2. Add the `w_member_social` and `r_liteprofile` OAuth scopes
3. Complete the OAuth 2.0 flow to obtain an `access_token`
4. Find your `person_urn` via `GET https://api.linkedin.com/v2/me` — it's the `id` field
5. POST both to `/linkedin/config`:
   ```json
   { "access_token": "...", "person_urn": "abc123" }
   ```

See [LinkedIn UGC Posts API docs](https://learn.microsoft.com/en-us/linkedin/marketing/integrations/community-management/shares/ugc-post-api) for full reference.

---

## EVA Architecture Fit

```
Layer 1 (Activity Stream)
    ↓  EVA logs: deals, patterns, builds, calendar
Content Engine (this module)
    ↓  Nightly generation → 3 draft posts
Draft Queue
    ↓  Morning OS review → approve / reject / edit
LinkedIn API
    ↓  Post on approval or schedule
Performance Tracker
    ↓  Metrics fed back into EVA activity stream
```

---

## How to Start

```bash
python main.py
```

Or via the EVA launcher:

```bash
~/Eva/eva-start.sh
```

Or full setup from scratch:

```bash
./setup.sh
```
