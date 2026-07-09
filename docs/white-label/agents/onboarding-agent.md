# OnboardingAgent

> The "manual morning → automated backend" bridge. Takes a new client brief and produces a live, configured Eva instance with zero manual steps.

## Trigger
CLI: `eva onboard --brief client.json` or backend job triggered from an intake form / admin UI.

## Input — ClientBrief
```json
{
  "client_name": "Storeys",
  "brand": { "name": "Storeys", "tagline": "...", "colors": {...}, "logo_url": "..." },
  "domain": "storeys.mangotec.ai",
  "crm_provider": "ghl",
  "ghl_location_id": "kyK4yAY6Hur3F4deCx2n",
  "landing_template": "acquisition-waitlist",
  "copy_overrides": { "hero_headline": "...", "cta_label": "Get early access" },
  "tags": ["storeys-cre", "investor"],
  "campaign_id": "<optional 7-touch campaign>",
  "directive_scope": "tenant"
}
```

## Steps (autonomous)
1. **Create tenant config** — mint `tenant_id`, write `TenantConfig` to config store.
2. **Generate landing** — render template with brand/copy overrides → static build.
3. **Wire CRM provider** — resolve provider (GHL default), confirm location access, map `locationId ↔ tenant_id`.
4. **Deploy landing** — via DeployProvider (Vercel or Eva-hosted); attach domain.
5. **Configure lead endpoint** — point form at tenant-scoped `/api/lead?tenant=<id>`; ensure token from vault.
6. **Smoke test** — POST a test lead, assert contact appears in CRM, assert row in audit log.
7. **Write onboarding report + directives** — save report to Drive KB, seed tenant directives, log decisions.

## Gates (configurable)
- Branding approval gate (pause for human sign-off on rendered landing before deploy) — open during testing.
- Cost gates on LLM-assisted copy generation.
- All gates configurable; "open all gates + collect data" mode for early training (per standing instruction).

## Outputs
- `tenant_id`
- live landing URL
- CRM contact created (smoke test)
- `onboarding-report.md` in workspace + Drive KB
- seeded `directives/tenant/<tenant_id>/index.md`

## Directives (learned over time)
- OnboardingAgent reads prior tenant onboardings to suggest copy, tags, campaign mapping.
- Promotes validated onboarding patterns to global directives.
