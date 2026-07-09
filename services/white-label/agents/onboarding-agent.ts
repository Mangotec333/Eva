/**
 * OnboardingAgent v0 — the "manual morning → automated backend" bridge.
 * Takes a ClientBrief and produces a live, configured Eva instance.
 *
 * CLI: eva onboard --brief client.json
 * Backend: triggered from intake form / admin UI.
 *
 * See docs/white-label/agents/onboarding-agent.md
 */

import { captureLead } from '../services/lead-capture-service';

export interface ClientBrief {
  client_name: string;
  brand?: { name?: string; tagline?: string; colors?: Record<string, string>; logo_url?: string };
  domain?: string;
  crm_provider?: 'ghl' | 'hubspot' | 'pipedrive' | 'sheet';
  ghl_location_id?: string;
  landing_template?: string;
  copy_overrides?: Record<string, string>;
  tags?: string[];
  campaign_id?: string;
  directive_scope?: 'tenant' | 'global';
}

export interface OnboardingResult {
  tenant_id: string;
  landing_url?: string;
  smoke_test: { ok: boolean; contactId?: string; error?: string };
  report_path: string;
}

function mintTenantId(name: string): string {
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  return `tenant-${slug}-${Date.now().toString(36).slice(-5)}`;
}

export async function onboard(brief: ClientBrief): Promise<OnboardingResult> {
  const tenantId = mintTenantId(brief.client_name);

  // 1. Write TenantConfig (TODO: config store)
  const tenantConfig = {
    tenant_id: tenantId,
    client_name: brief.client_name,
    brand: brief.brand || {},
    domain: brief.domain || '',
    crm_provider: brief.crm_provider || 'ghl',
    ghl_location_id: brief.ghl_location_id || '',
    deploy_provider: 'eva-hosted' as const,
    landing_template: brief.landing_template || 'acquisition-waitlist',
    copy_overrides: brief.copy_overrides || {},
    tags: brief.tags || [],
    campaign_id: brief.campaign_id || '',
    directive_scope: brief.directive_scope || 'tenant',
    created_at: new Date().toISOString()
  };

  // 2. Generate landing (TODO: render template with brand/copy overrides)
  // 3. Wire CRM provider (resolve by tenantConfig.crm_provider)
  // 4. Deploy landing (TODO: DeployProvider)
  // 5. Configure lead endpoint
  // 6. Smoke test — POST a test lead, assert contact in CRM
  const smoke = await captureLead(
    {
      name: `${brief.client_name} Smoke Test`,
      email: `smoke-${tenantId}@mangotecusa.com`,
      investor_type: 'Get early access',
      message: 'OnboardingAgent smoke test'
    },
    tenantId,
    tenantConfig.crm_provider
  );

  // 7. Write onboarding report + seed directives (TODO: Drive KB + directive store)
  const report_path = `directives/tenant/${tenantId}/onboarding-report.md`;

  return {
    tenant_id: tenantId,
    smoke_test: smoke,
    report_path
  };
}
