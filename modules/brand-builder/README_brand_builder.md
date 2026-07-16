# EVA Brand-Builder (`:8792`)

Eva's **brand strategy / orchestration layer**. It sits **above**
`content-engine` (`:8767`, makes content) and `social-scheduler` (`:8787`,
approves + posts). The Brand Builder **writes content BRIEFS — it never posts.**
Approval stays **L1**: drafts only, the user approves before anything goes out
(`approval_required: true` on every pipeline and brief).

```
brand-builder (:8792)   strategy — writes briefs
        │  brand_brief_created (eva-state event)
        ▼
content-engine (:8767)  drafts copy from the brief
        │
        ▼
social-scheduler (:8787)  approve (L1) → post
```

## Core objects

Stored as plain JSON under `~/.eva/brand_builder/` (override with `EVA_BRAND_DIR`),
config-file-primary like `social-publish`:

- `pipelines/<pipeline_id>.json` — one strategy pipeline:
  `{pipeline_id, category, mission, target_audience, current_goal, offer, cta,
  positioning, proof_assets[], content_pillars[], voice_rules[],
  approval_required, success_metric, blueprint_version}`
- `blueprints/<category-slug>.json` — one market blueprint per category:
  `{audience, market_patterns[], channels[], content_archetypes[],
  authority_signals[], awareness_loops[], cadence{}, cta_ladder[], do_not_say[],
  kpis[]}`. Each `market_pattern` carries `date + source_url + confidence`
  (`high`/`med`/`low`).
- `personas/<name>.json` — persistent persona configs (NOT always-running
  agents): `awareness_persona`, `authority_persona`, `brand_persona`, each
  `{focus, hooks[], archetypes[], channels[], tone}`.
- `briefs/<brief_id>.json` — content briefs (pending → queued).

## The first pipeline

Seeded from `seed/brand_blueprint_eva_growth_agency.md` (the **source of truth**
for the Eva Growth Agency pipeline). The blueprint markdown is parsed
deterministically into `pipeline.json` + `blueprint.json` + the three personas.

```bash
python seed.py                 # seed the first pipeline
python main.py --seed          # same, via the service
```

## API (port 8792, FastAPI)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Health + offline flag + loop state |
| GET | `/brand/status` | Pipelines / blueprints / personas / pending briefs / stale blueprints |
| GET | `/brand/pipelines` | All pipelines |
| GET | `/brand/pipelines/{id}` | One pipeline |
| GET | `/brand/blueprints/{category}` | One blueprint (by category name or slug) |
| POST | `/brand/seed` | Seed a pipeline from the blueprint md |
| POST | `/brand/plan` | Weekly content plan → list of briefs (`{pipeline_id, timeframe}`) |
| GET | `/brand/briefs` | Pending / queued briefs |
| POST | `/brand/queue` | Emit briefs to content-engine via `brand_brief_created` |
| POST | `/brand/refresh` | Re-check blueprints for staleness |

Also exposed via the launcher on `:8768` as lazy `/brand/*` routes.

## Planning

`POST /brand/plan` turns a pipeline + blueprint + personas into a week of briefs.
Cadence comes straight from the blueprint's section-7 table (Daily X, 3x/week
LinkedIn, weekly newsletter, …). Each brief is assigned an archetype (round-robin
over the blueprint's content archetypes), a persona (via `personas.select_persona`),
a hook (from the matching awareness loop), the pipeline CTA, a rotating proof
asset, and the pipeline's `voice_rules` + `do_not_say` guardrails.

## Integration & loops

- **eva-state** (`:8769`) via `state_client` — emits `brand_pipeline_seeded`,
  `brand_plan_created`, `brand_brief_created`, `brand_blueprint_stale`.
- **Weekly refresh loop** (`86400 * 7 s`) re-checks blueprints: any whose
  `blueprint_version` is older than 7 days emits `brand_blueprint_stale`.

## Offline mode

`EVA_BRAND_OFFLINE=1` (sandbox default) → eva-state emits are stubbed (no
network) and missing pipelines/blueprints fall back to mocked objects so every
endpoint still returns a usable shape. Tests run fully offline, mocked, with zero
real API calls.

```bash
EVA_BRAND_OFFLINE=1 python test_brand_builder.py
```
