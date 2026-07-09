/**
 * GHLProvider — GoHighLevel implementation of CRMProvider.
 *
 * Uses the GHL Contacts API: POST https://services.leadconnectorhq.com/contacts/
 * Headers: Authorization: Bearer <token>, Version: 2021-07-28
 *
 * Token source (production): tenant credential vault (OAuth via Eva Marketplace app).
 * Token source (prototype): env var GHL_API_KEY (single-tenant; rotate after Marketplace app live).
 *
 * See docs/white-label/provider-contracts/crm-provider.md, docs/white-label/security/tenant-isolation.md
 */

import type { CRMProvider, LeadInput, OpportunityInput, Campaign, Stage } from './crm-provider';

const GHL_API_BASE = 'https://services.leadconnectorhq.com';

function splitName(full: string): { firstName: string; lastName: string } {
  const parts = (full || '').trim().split(/\s+/);
  if (parts.length <= 1) return { firstName: parts[0] || '', lastName: '' };
  return { firstName: parts[0], lastName: parts.slice(1).join(' ') };
}

// Placeholder for the tenant credential vault. Real impl resolves an OAuth
// token by tenant_id from an encrypted store. Prototype reads env var.
async function getToken(tenantId: string): Promise<string> {
  // TODO: tenant vault: vault.get(tenantId, 'ghl_token')
  const token = process.env.GHL_API_KEY;
  if (!token) throw new Error('GHL_API_KEY not configured (prototype path)');
  return token;
}

async function getLocationId(tenantId: string): Promise<string> {
  // TODO: resolve from TenantConfig store
  return process.env.GHL_LOCATION_ID || 'kyK4yAY6Hur3F4deCx2n';
}

export class GHLProvider implements CRMProvider {
  readonly provider = 'ghl';

  async healthCheck(tenantId: string) {
    try {
      await this.listCampaigns(tenantId);
      return { ok: true, provider: this.provider };
    } catch {
      return { ok: false, provider: this.provider };
    }
  }

  async createOrUpdateLead(input: LeadInput, tenantId: string) {
    const token = await getToken(tenantId);
    const locationId = await getLocationId(tenantId);
    const { firstName, lastName } = splitName(input.name);

    const body = {
      locationId,
      firstName,
      lastName,
      name: input.name,
      email: input.email,
      phone: input.phone,
      companyName: input.company || '',
      source: input.source || 'Eva platform',
      tags: input.tags || []
    };

    const resp = await fetch(`${GHL_API_BASE}/contacts/`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
        Version: '2021-07-28'
      },
      body: JSON.stringify(body)
    });

    if (!resp.ok) {
      const txt = await resp.text();
      throw new Error(`GHL createLead failed ${resp.status}: ${txt}`);
    }
    const data = await resp.json();
    const contactId = data?.contact?.id;
    if (!contactId) throw new Error('GHL createLead: no contact id returned');
    return { contactId, created: true };
  }

  async addTag(_contactId: string, _tag: string, _tenantId: string) { throw new Error('not implemented v0'); }
  async updateContact(_contactId: string, _patch: Partial<LeadInput>, _tenantId: string) { throw new Error('not implemented v0'); }
  async createOpportunity(_input: OpportunityInput, _tenantId: string) { throw new Error('not implemented v0'); }
  async moveOpportunity(_opportunityId: string, _stageId: string, _tenantId: string) { throw new Error('not implemented v0'); }
  async enrollInCampaign(_contactId: string, _campaignId: string, _tenantId: string) { throw new Error('not implemented v0'); }
  async listCampaigns(_tenantId: string): Promise<Campaign[]> { return []; }
  async listPipelineStages(_tenantId: string): Promise<Stage[]> { return []; }
}
