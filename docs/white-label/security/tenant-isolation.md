# Tenant Isolation & Directive Promotion

> The #1 architectural risk. Get this right from day 1; retrofitting is painful.

## 1. Tenant isolation rules

- **Every record carries `tenant_id`** — leads, deals, contacts, prompts, directives, credentials, audit logs, agent memory. No exceptions.
- **No agent memory, lead, deal, or directive is queryable without tenant scope.** All DB queries, agent contexts, and API handlers enforce `WHERE tenant_id = ?`.
- **Credentials are tenant-scoped** — encrypted token vault keyed by `tenant_id`; never single-tenant env vars in production.
- **PII never trains shared models.** Raw investor/contact PII stays within its tenant.

## 2. Directive promotion pipeline (the data flywheel, done safely)

Raw tenant data is NOT shared across clients. Instead, an explicit, auditable pipeline extracts and promotes learnings:

```
raw tenant data (PII, scoped)
  → DirectiveExtractionAgent (tenant-scoped): extracts patterns, templates, playbooks
  → tenant directives (still scoped)
  → [HUMAN/QUALITY GATE] promotion review
  → global directives (anonymized, shared across tenants)
```

- **Extraction is tenant-scoped** — an agent reads one tenant's data and writes directives for that tenant only.
- **Promotion is explicit + auditable** — validated patterns are reviewed (gate configurable; open during testing to collect data) then promoted to global directives.
- **Global directives are anonymized** — no PII, no client-identifying detail.

## 3. Directive store

```
directives/
  global/
    index.md              # shared learned directives (promoted)
    onboarding.md
    deal-scoring.md
  tenant/
    <tenant_id>/
      index.md            # tenant-specific directives
      onboarding.md
      <agent>.md
```

- Indexed for session restarts (agents reload their directives on start).
- Promotion log: `directives/promotion-log.md` — what was promoted, when, from which tenant, by whom/gate.

## 4. Audit

Every state-changing agent action writes to an audit row:
`{ tenant_id, agent, action, target, timestamp, gate_status }`.

## 5. Compliance (forward-looking)

- GDPR/CCPA: per-tenant data export + delete endpoints.
- Eventually SOC 2 expectations as client count grows.
- Data lifecycle (per standing instruction): active → train/extract directives → archive/purge raw PII to backlog storage.
