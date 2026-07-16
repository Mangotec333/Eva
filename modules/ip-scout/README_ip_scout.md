# EVA IP-Scout — Prior-Art Triage (`:8791`)

IP-Scout is Eva's **L1-autonomy** invention-triage lobe. It runs a **daily
incremental** novelty / prior-art triage over invention-idea seeds and surfaces
what's worth a **patent attorney's review**.

> **L1 autonomy — it never files anything.** IP-Scout triages and reports only.
> It never files, submits to the USPTO (or any authority), or asserts
> patentability. Novelty scores are heuristic signals to prioritise a human
> attorney's review.

## Sensors (hybrid)

1. **User-seeded ideas** — `~/.eva/ip_ideas.json` (override `EVA_IP_IDEAS_FILE`).
   Each record: `id, title, description, category, seeded_at, status`.
2. **Eva-activity mining** — mines the eva-state ledger (`:8769`) for repeatable
   process patterns that could be invention disclosures (`mining.py`, v1 stub;
   NLP clustering is phase-2 behind the same interface).

## What a scan produces

Each pending idea becomes an **invention disclosure**:

```
{idea_id, title, abstract, claims_draft, sensor_source, created_at,
 novelty_score, confidence_band, prior_art_hits[], status,
 attorney_review_needed, recommendation}
```

* **Prior-art provider** — pluggable (`provider.py`). v1 ships PatentsView
  (config-file-primary key) + an offline mock. USPTO Open Data is phase-2 behind
  the same `PriorArtProvider` interface.
* **Novelty scoring** (`novelty.py`) — deterministic `novelty_score ∈ [0,1]` from
  token overlap against prior art + claim specificity, plus a `confidence_band`
  (low/med/high) from how much prior-art evidence was examined.
* **Recommendation** — `file` / `monitor` / `drop` per idea. Low confidence never
  confidently files or drops (caps at monitor).
* **Daily markdown report** — `~/.eva/ip_scout/reports/<date>.md`, grouped by
  recommendation, "needs attorney review" throughout.

## API (port 8791)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/ip/status` | module status + sensors + last run + reports |
| GET | `/ip/ideas` | all idea seeds (`?status=pending\|triaged`) |
| GET | `/ip/idea/{id}` | one idea + its latest disclosure |
| POST | `/ip/seed` | add an invention idea seed |
| POST | `/ip/scan` | trigger a triage run over pending ideas |
| GET | `/ip/history` | past triage runs (newest first) |
| GET | `/ip/report/{date}` | the daily markdown report for a date |

Also exposed on the launcher (`:8768`) via lazy import under the same `/ip/*`
paths.

## Configuration

PatentsView key (optional — offline mock is used without it):

```json
// ~/.eva/channels_config.json
{ "ip_scout": { "patentsview_api_key": "..." } }
```

Env fallback: `PATENTSVIEW_API_KEY`.

## Env vars

| Var | Effect |
| --- | --- |
| `EVA_IP_OFFLINE=1` | mocked provider + stubbed eva-state, no network (sandbox default) |
| `EVA_IP_NO_LOOP=1` | don't start the daily loop |
| `EVA_IP_DIR` | override the data dir (default `~/.eva/ip_scout`) |
| `EVA_IP_IDEAS_FILE` | override the ideas json (default `~/.eva/ip_ideas.json`) |
| `PATENTSVIEW_API_KEY` | PatentsView key env fallback |

## Run

```bash
cd modules/ip-scout && python3 main.py            # serve on :8791
python3 main.py --scan                             # one scan, print result
python3 seed.py --title "..." --desc "..." --scan  # seed + scan
python3 test_ip_scout.py                           # offline test suite
```
