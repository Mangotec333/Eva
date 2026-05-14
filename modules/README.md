# EVA Modules

Standalone modules that power EVA's sensing and operating layers.
Each module is independently deployable and validates as a micro-SaaS candidate.

## modules/logger — EVA Activity Logger

EVA's sensing layer. Tracks app usage, screen activity, and audio transcripts.
Three-tier source hierarchy: Screenpipe → ActivityWatch → built-in daemon.

**Key files:**
- `eva_logger.py` — background daemon, JSONL activity log
- `eva_activitywatch_bridge.py` — ActivityWatch REST client + normalizer
- `eva_screenpipe_bridge.py` — Screenpipe REST client (OCR + audio)
- `eva_context_api.py` — unified REST API on :8765 for EVA agents
- `eva_summarize.py` — daily summary + focus score generator

**Quick start:**
```bash
cd modules/logger
bash setup.sh
python eva_logger.py &
python eva_context_api.py
```

**API endpoints:**
- `GET localhost:8765/context/unified` — all sources merged
- `GET localhost:8765/screenpipe/search?q=<query>` — search screen memory
- `GET localhost:8765/screenpipe/transcript?start=...&end=...` — meeting transcript

## modules/morning-os — EVA Morning OS

EVA's daily operating system. Opens in browser each morning.
Goal check-in across time horizons, priority surfacing, activity dashboard.

**Stack:** Express + Vite + React + Tailwind + shadcn/ui + Drizzle/SQLite

**Quick start:**
```bash
cd modules/morning-os
npm install
npm run dev
```

**Live deployment:** https://www.perplexity.ai/computer/a/eva-morning-os-3Tmx6H6.SsOgfEUZegsOJw
