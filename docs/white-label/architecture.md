# Eva — White-Label Architecture Spec

> Status: v0.1 — 2026-07-08
> Owner: Mangotec (Eva platform)
> Standing principles: every task = an Eva agent/microservice; provider-abstraction (swap & play); data flywheel; index all directives for session restarts and long-term learning.

## 1. Vision

Eva is Mangotec's multi-tenant, white-label AI agent platform for M&A / business-acquisition firms (senior-care CRE, e-commerce roll-ups, search funds,_holdcos). Each client gets a branded instance with: a lead-capture landing page, a CRM (GoHighLevel default), and a fleet of autonomous agents that source, score, and action deals. Mangotec owns the master platform; clients authorize Eva into their tools via OAuth.

## 2. Core Principles (non-negotiable)

1. **Tenant isolation first** — every record carries `tenant_id`; no cross-tenant data access by default. PII never trains shared models directly.
2. **Provider abstraction** — CRM, deploy, domain, and directive layers are swappable interfaces. GHL is the default implementation; HubSpot/Pipedrive/Sheets implement the same contract.
3. **Agents as microservices** — each capability is an autonomous agent with its own directives, gated by configurable cost gates.
4. **Data flywheel** — raw tenant data → extracted directives → promoted global directives via an explicit, auditable promotion pipeline. Raw PII stays tenant-scoped.
5. **Index everything** — directives, decisions, and config live in a queryable store so agents restart with full context.

## 3. GHL White-Label Topology

```
Mangotec GHL Agency (Pro + SaaS Mode)
  ├─ Client A location (subaccount)  ← Eva Marketplace app installed
  ├─ Client B location (subaccount)  ← Eva Marketplace app installed
  └─ ...
Eva Marketplace OAuth App (Mangotec-owned, GHL-reviewed)
  → install flow returns location-scoped OAuth token
  → token stored encrypted in Eva's tenant credential vault
  → maps locationId ↔ tenant_id
```

- **No per-client Private Integration tokens** in production. (The pit-… token used for the prototype must be rotated once the Marketplace app + token vault are live.)
- **Do not build production on Pipedream connectors** — those were operator convenience only.

## 4. Build Sequence (prioritized)

1. **Spec docs** (this + sub-docs) — saved to repo + Drive KB.
2. **TenantConfig schema** — canonical per-client config.
3. **LeadCaptureService v1** — promote today's `/api/lead` into a provider-backed, tenant-scoped service with a mock provider for tests.
4. **OnboardingAgent v0** — the "manual morning → automated backend" bridge.
5. **GHL Marketplace OAuth app** — subaccount install flow, OAuth callback, token vault, locationId→tenant_id mapping.
6. **Directive store** — tenant-scoped directives + global promoted directives.

## 5. Account & Tooling Plan

- **GHL Production agency** (Agency Pro + SaaS Mode) — Mangotec-owned, hosts real client subaccounts.
- **GHL Dev/Sandbox agency** — test Marketplace OAuth, dummy clients.
- **Eva GitHub org**: `Mangotec333/Eva` (repo for the platform).
- **Hosting**: Eva master deployment on pplx.app / Vercel; per-client landings on Vercel or Eva-hosted subdomains.
- **Credential vault**: encrypted table for per-tenant OAuth tokens (refresh rotation, revocation, audit, install/uninstall).

## 6. Profitable Economies (recap)

| Lever | Range | Notes |
|---|---|---|
| Per-location SaaS | $99–$499/mo | core recurring |
| Onboarding setup fee | $1k–$5k | near-pure margin via OnboardingAgent |
| Usage credits | usage-based | agent runs, deal scoring |
| Deal rev-share | 1–3% | high upside |
| GHL SaaS-mode markup | $100–$300/mo spread | per location |

Floor at 50 locations: ~$30k–$60k MRR, 70%+ margin.

## 7. Sub-Docs

- `docs/white-label/agents/onboarding-agent.md` — OnboardingAgent spec
- `docs/white-label/provider-contracts/crm-provider.md` — CRM provider interface
- `docs/white-label/provider-contracts/deploy-provider.md` — Deploy/Domain provider interface
- `docs/white-label/security/tenant-isolation.md` — isolation rules + directive promotion pipeline
