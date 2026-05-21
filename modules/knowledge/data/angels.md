# EVA Angels Framework
_Last updated: 2026-05-21 | Version: 0.3 | Module: EVA Knowledge OS_

EVA's autonomous agent layer. Each angel runs independently, reads from Knowledge OS, writes learnings back. Together they form a self-improving operating system.

## Naming Principle
Functional names — each name describes the role directly. These are not tools. They are guardians.

## The 17 Angels

| # | Name | Mythology/Origin | Role | Port/Schedule | Status |
|---|---|---|---|---|---|
| 0 | **Sentinel** | Roman — eternal watcher | Watchdog — 5min port check, auto-restart dead services | cron every 5min | ✅ Built |
| 1 | **Scout** | — | Idea & Pattern Scout — identifies patterns across all EVA activity weekly | cron weekly | 📋 Queued |
| 2 | **Moat** | — | Identifies defensible competitive advantages being built | cron weekly | 📋 Queued |
| 3 | **Yaksha** | Hindu — wealth guardian, protector of treasures | Monetization Scanner — daily money move | cron 7am PT daily | ✅ Built |
| 4 | **Archivist** | — | Organizes, tags, structures all EVA knowledge | cron daily | 📋 Queued |
| 5 | **Pruner** | — | Deprioritizer — kills zombie tasks every 15min | cron 15min | 📋 Queued |
| 6 | **Rainmaker** | — | Trend finder — emerging market signals, distribution angles | cron daily | 📋 Queued |
| 7 | **Guardian** | — | Security — token expiry, credential rotation, data protection | cron hourly | 📋 Queued |
| 8 | **Planner** | — | Planner — weekly/monthly plan synthesis from all angel outputs | cron weekly Sunday | 📋 Queued |
| 9 | **Ledger** | — | Capital burn monitor — tracks HELOC spend vs revenue generated | cron daily | 📋 Queued |
| 10 | **Mirror** | — | Reflection agent — compares decisions made vs outcomes | cron weekly | 📋 Queued |
| 11 | **Researcher** | — | Research agent — deep dives on any topic on demand | on-demand | 📋 Queued |
| 12 | **Outreach** | — | Outreach agent — drafts and tracks all DMs/emails | on-demand | 📋 Queued |
| 13 | **Publisher** | — | Content weaver — turns EVA activity into LinkedIn/Twitter posts | cron daily | 📋 Queued |
| 14 | **Pulse** | — | Wellness check — tracks energy, focus, family time balance | cron morning | 📋 Queued |
| 15 | **Synthesis** | — | Meta-angel — reads all others, outputs one page weekly brief | cron Sunday 8am | 📋 Queued |
| 16 | **Funnel Builder** | GoHighLevel | Builds GHL funnels from validated Incubation Lab ideas | on-demand | 📋 Queued |

## Build Priority

**Now:** Yaksha ✅ → Sentinel ✅ → Guardian → Pruner
**Month 1:** Ledger → Rainmaker → Planner
**Month 2+:** All remaining

## API Contract (all angels must follow)
Every angel reads: `GET /knowledge/context` — full founder context
Every angel writes: `POST /knowledge/experiments/append` — logs findings
Every angel outputs to: `~/.eva/angels/{name}_daily.json`
Every angel logs to: `~/.eva/angels/{name}_log.jsonl`

## The Meta Principle
Synthesis (Angel 15) reads all other angels and produces one page every Sunday morning. That page is your week. Everything else is noise.
