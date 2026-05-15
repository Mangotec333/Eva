# EVA — Master Status Document
**Owner:** Vineetkumar Ravi · vineetkumar@mangotecusa.com · Mangotec LLC, Los Angeles CA
**Repo:** [Mangotec333/Eva](https://github.com/Mangotec333/Eva) · **Latest commit:** `aaa0c76`
**Live:** [eva.mangotec.ai](https://eva.mangotec.ai) (Netlify) · **Session PIN:** 557799 (8-hr)

---

## 🔴 BLOCKING RIGHT NOW

| # | Issue | Action |
|---|---|---|
| 1 | **Services not starting on Mac** — Launcher `:8768` online, LAUNCH ALL fires 5 Terminal tabs, but 0/5 services come up | Run commands below, then share Terminal tab screenshot |
| 2 | **LinkedIn OAuth** — Content Engine built & ready, blocked on credentials | Get `access_token` + `person_urn` from LinkedIn Developer portal |
| 3 | **Netlify CI/CD** — every deploy requires manual zip upload | Add `netlify.toml` to repo; wire GitHub → Netlify auto-deploy |

**Service startup fix (run in order):**
```bash
cd ~/Eva && git pull
bash ~/Eva/eva-install-deps.sh
bash ~/Eva/eva-start.sh
```

---

## 🟡 PENDING / IN PROGRESS

| Item | Status | Next Step |
|---|---|---|
| **Lovable Bridge (Module 8)** | Ready to test | `pip3 install fastapi uvicorn` in `modules/lovable-bridge/`, then POST `/build` |
| **Claude Local Data** | Script written, not yet run | Run `~/Eva/docs/find-claude-logs.sh` |
| **EVA Launcher on startup** | launchd plist installed | Verify it fires correctly after a full reboot |

---

## NEXT STEPS — PRIORITY ORDER

1. Fix services startup — screenshot Terminal tab errors after `eva-start.sh`
2. LinkedIn OAuth — wire `access_token` + `person_urn` into Content Engine
3. Netlify CI/CD — `git push` → auto-deploy to `eva.mangotec.ai`
4. Lovable Bridge — fire first `/build` call, build a module via Lovable
5. Verify launchd auto-start survives reboot

---

## EVA MODULES

| # | Module | Port | Path | Status |
|---|---|---|---|---|
| 1 | Logger + ActivityWatch + Screenpipe bridges | — | `modules/logger/` | ✅ Built |
| 2 | Morning OS (React/Vite) | 5173 | `modules/morning-os/` | ✅ Built |
| 3 | Deal Scout v2 (FastAPI) | 8766 | `modules/deal-scout/` | ✅ Built |
| 4 | Command Center v3 (React/Vite) | 5173 | `modules/command-center/` | ✅ Built + Deployed |
| 5 | Content Engine (FastAPI) | 8767 | `modules/content-engine/` | ✅ Built |
| 6 | Auto-Start (launchd + watchdog) | — | `modules/autostart/` | ✅ Built |
| 7 | Launcher API (FastAPI) | 8768 | `modules/launcher/` | ✅ Built |
| 8 | Lovable Bridge (FastAPI) | 8769 | `modules/lovable-bridge/` | 🟢 Ready to test |

**Content Engine profiles:** `thought_leader` · `builder_log` · `human_story`

---

## INFRASTRUCTURE

### Hosting & Repos
| Resource | Detail |
|---|---|
| **Live URL** | [eva.mangotec.ai](https://eva.mangotec.ai) — Netlify static React, GoDaddy CNAME |
| **GitHub** | [Mangotec333/Eva](https://github.com/Mangotec333/Eva) |
| **AJORA** | [Mangotec333/ajora](https://github.com/Mangotec333/ajora) — provisional patent, 8-layer agent architecture |

### Local Mac Paths
| Purpose | Path |
|---|---|
| Repo | `~/Eva/` |
| Logs | `~/Eva/logs/` |
| Activity data | `~/eva-data/` |
| Clone fresh | `git clone https://github.com/Mangotec333/Eva.git ~/Eva` |

### Key Scripts
| Script | Purpose |
|---|---|
| `bash ~/Eva/eva-install-deps.sh` | Install all Python deps (run once) |
| `bash ~/Eva/eva-start.sh` | Launch all services |
| `bash ~/Eva/eva-stop.sh` | Stop all services |
| `bash ~/Eva/modules/autostart/eva-install-services.sh` | Install launchd auto-start |

### API Reference
**Context API `:8765`**
- `GET /context/unified` · `/context/today` · `/context/week` · `/context/patterns` · `/context/recent`
- `GET /screenpipe/search` · `/screenpipe/context/recent` · `/screenpipe/status`

**Deal Scout API `:8766`**
- Pipeline stages: `tracking → in_progress → nda_signed → loi_sent → due_diligence → closed`
- `GET /deals/pipeline` · `/deals/archived` · `/deals/{id}/history`
- `POST /deals/{id}/stage` · `/deals/{id}/archive`

---

## ACQUISITION SHORTLIST (Deal Scout)

| Business | Source | Score | AI-Proof | Net/Mo | Status |
|---|---|---|---|---|---|
| Digital Media Services | EF #87872 | 9.1 | 84 ✅ | ~$9,800 | 🟡 Active |
| Education Tutoring | Flippa #12166327 | 8.5 | 82 ✅ | $6,226 | 🟡 Active |
| Real Estate Comparison | Flippa #12032980 | 8.3 | 68 | $11,664 | 🟡 Active |
| WordPress Plugin (13yr) | Flippa #12278661 | 7.2 | 61 | $5,889 | 🟡 Active |
| Digital Products Art | EF #89115 | PASS | 38 ⚠️ | — | ❌ Archived |

**Note:** Empire Flippers uses monthly multiples (18x = 18 months). Flippa uses annual multiples.

---

## LIFE ARCHITECTURE

### Priority Stack
| # | Priority |
|---|---|
| 1 | EVA mornings |
| 2 | AI Growth Agency → $10K/mo |
| 3 | Wife & family |
| 4 | Public Speaking (Leadr.co) |
| 5 | Storeys (storeys.io — RCFE acquisitions, CA senior care) |
| 6 | Pureplate (dropshipping e-commerce) |

**Threshold:** $10K net/month = arrow flips
**90-day target:** First paying AI agency client OR digital business acquisition
**HELOC:** $200K @ 9.5% (interest only ~$1,583/mo on full draw)

### Core Fires
- **Fire #1:** Building autonomous AI systems — EVA / AJORA
- **Fire #2:** Communicating an idea and watching it land

### Hedgehog / Flywheel (Jim Collins)
Applied: Hedgehog Concept · Level 5 Leadership · First Who Then What · Flywheel — all mapped to EVA context.

---

## ✅ ARCHIVED (completed, closed out)

| Item | Output |
|---|---|
| **Life Architecture Exercise** | PDF + visual created and shared |
| **Signature Talk** — *"Logic, Intuition & The LLM Within You"* | Framework captured, Leadr.co workshop notes ingested → `~/Eva/docs/signature-talk.md` |
| **Empire Flippers Research** | 35-listing spreadsheet, top-3-per-category sort, final shortlist with AI-Proof scores (above) |
| **Jim Collins / Good to Great** | Applied to EVA context |

---

*Last updated: this session. Edit at `~/Eva/docs/EVA_STATUS.md` or regenerate via EVA.*
