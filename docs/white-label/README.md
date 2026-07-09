# Eva — White-Label Agent Platform

Multi-tenant, white-label AI agent platform for M&A / business-acquisition firms. Each client gets a branded instance: lead-capture landing, CRM (GoHighLevel default), and autonomous agents that source, score, and action deals.

## Standing principles
1. Every task = an Eva agent/microservice.
2. Provider abstraction — CRM, deploy, domain, directive layers are swappable (swap & play).
3. Data flywheel — raw tenant data → extracted directives → promoted global directives (explicit, auditable).
4. Index all directives for session restarts and long-term learning.
5. Tenant isolation first — every record carries `tenant_id`; PII never trains shared models.

## Repo layout (v0)
```
docs/white-label/
  architecture.md                      # top-level spec
  agents/onboarding-agent.md
  provider-contracts/crm-provider.md
  provider-contracts/deploy-provider.md
  security/tenant-isolation.md
config/
  tenant-config.schema.json            # canonical per-client config
services/white-label/                  # TS v0 scaffold (to be ported to Python — see NOTE.md)
  providers/
    crm-provider.ts                    # CRM interface
    ghl-provider.ts                    # GHL implementation
  services/
    lead-capture-service.ts            # tenant-scoped lead capture
  agents/
    onboarding-agent.ts                # OnboardingAgent v0
```

## Build sequence (prioritized)
1. Spec docs (done v0) + Drive KB sync
2. TenantConfig schema + store
3. LeadCaptureService v1 (provider-backed; promotes eva-landing /api/lead)
4. OnboardingAgent v0 (manual morning → automated backend)
5. GHL Marketplace OAuth app + token vault (kills per-client PIT friction)
6. Directive store + promotion pipeline

## Status
- v0 spec + scaffold authored 2026-07-08.
- Prototype: eva-landing live at https://eva-acquisition.mangotec.ai with working /api/lead → GHL (PIT token in Vercel env; rotate after Marketplace app).
- 7 investor contacts imported to GHL location kyK4yAY6Hur3F4deCx2n.

## Next
- Stand up GHL agency account (Pro + SaaS Mode) for white-label resale.
- Publish Eva as GHL Marketplace OAuth app (dev sandbox → prod).
- Wire OnboardingAgent to real DeployProvider + Drive KB report writer.
