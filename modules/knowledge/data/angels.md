# EVA Angels Framework
_Last updated: 2026-05-21 | Version: 0.2 | Module: EVA Knowledge OS_

EVA's autonomous agent layer. Each angel runs independently, reads from Knowledge OS, writes learnings back. Together they form a self-improving operating system.

## Naming Principle
Indian mythology + Greek mythology — each name carries the energy of its role. These are not tools. They are guardians.

## The 16 Angels

| # | Name | Mythology | Role | Port/Schedule | Status |
|---|---|---|---|---|---|
| 0 | **Sentinel** | Roman — eternal watcher | Watchdog — 5min port check, auto-restart dead services | cron every 5min | 📋 Queued |
| 1 | **Iris** | Greek — messenger of gods | Idea & Pattern Scout — identifies patterns across all EVA activity weekly | cron weekly | 📋 Queued |
| 2 | **Moat Builder** | — | Identifies defensible competitive advantages being built | cron weekly | 📋 Queued |
| 3 | **Yaksha** | Hindu — wealth guardian, protector of treasures | Monetization Scanner — daily money move | cron 7am PT daily | ✅ Built |
| 4 | **Archivist** | — | Organizes, tags, structures all EVA knowledge | cron daily | 📋 Queued |
| 5 | **Brahma** | Hindu — creator, destroyer of what no longer serves | Deprioritizer — kills zombie tasks every 15min | cron 15min | 📋 Queued |
| 6 | **Rainmaker** | — | Trend finder — emerging market signals, distribution angles | cron daily | 📋 Queued |
| 7 | **Kavach** | Sanskrit — divine armor, shield | Security — token expiry, credential rotation, data protection | cron hourly | 📋 Queued |
| 8 | **Sutra** | Sanskrit — thread that binds | Planner — weekly/monthly plan synthesis from all angel outputs | cron weekly Sunday | 📋 Queued |
| 9 | **Karma** | Hindu — law of action and consequence | Capital burn monitor — tracks HELOC spend vs revenue generated | cron daily | 📋 Queued |
| 10 | **Mirror** | — | Reflection agent — compares decisions made vs outcomes | cron weekly | 📋 Queued |
| 11 | **Veda** | Sanskrit — knowledge, sacred text | Research agent — deep dives on any topic on demand | on-demand | 📋 Queued |
| 12 | **Hermes** | Greek — messenger, commerce | Outreach agent — drafts and tracks all DMs/emails | on-demand | 📋 Queued |
| 13 | **Loom** | — | Content weaver — turns EVA activity into LinkedIn/Twitter posts | cron daily | 📋 Queued |
| 14 | **Soma** | Sanskrit — nectar of life | Wellness check — tracks energy, focus, family time balance | cron morning | 📋 Queued |
| 15 | **Synthesis** | — | Meta-angel — reads all others, outputs one page weekly brief | cron Sunday 8am | 📋 Queued |

## Build Priority

**Now:** Yaksha ✅ → Sentinel → Kavach → Brahma
**Month 1:** Karma → Rainmaker → Sutra
**Month 2+:** All remaining

## API Contract (all angels must follow)
Every angel reads: `GET /knowledge/context` — full founder context
Every angel writes: `POST /knowledge/experiments/append` — logs findings
Every angel outputs to: `~/.eva/angels/{name}_daily.json`
Every angel logs to: `~/.eva/angels/{name}_log.jsonl`

## The Meta Principle
Synthesis (Angel 15) reads all other angels and produces one page every Sunday morning. That page is your week. Everything else is noise.
