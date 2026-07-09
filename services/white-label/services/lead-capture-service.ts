/**
 * LeadCaptureService v1 — provider-backed, tenant-scoped lead capture.
 * Promotes the working eva-landing /api/lead function into the Eva platform.
 *
 * Flow: inbound lead → resolve tenant → resolve CRMProvider → createOrUpdateLead
 *
 * See docs/white-label/architecture.md, docs/white-label/security/tenant-isolation.md
 */

import type { CRMProvider, LeadInput } from '../providers/crm-provider';
import { GHLProvider } from '../providers/ghl-provider';

// Provider registry — swap & play. Selected by TenantConfig.crm_provider.
const providers: Record<string, CRMProvider> = {
  ghl: new GHLProvider()
  // hubspot: new HubSpotProvider(),
  // pipedrive: new PipedriveProvider(),
  // sheet: new SheetProvider(),
};

export interface InboundLead {
  name?: string;
  email?: string;
  phone?: string;
  investor_type?: string;
  message?: string;
}

export interface CaptureResult {
  ok: boolean;
  contactId?: string;
  error?: string;
  auditId?: string;
}

function investorTypeTag(t?: string): string | undefined {
  if (!t) return undefined;
  return 'want-' + t.toLowerCase().replace(/\s+/g, '-');
}

export async function captureLead(
  raw: InboundLead,
  tenantId: string,
  crmProviderName = 'ghl'
): Promise<CaptureResult> {
  const provider = providers[crmProviderName];
  if (!provider) return { ok: false, error: `unknown provider: ${crmProviderName}` };

  const email = (raw.email || '').toString().trim();
  if (!email || email.indexOf('@') === -1) return { ok: false, error: 'invalid_email' };

  const lead: LeadInput = {
    name: (raw.name || '').slice(0, 200),
    email,
    phone: raw.phone,
    source: 'Eva platform lead capture',
    tags: ['eva-acquisition', 'waitlist', investorTypeTag(raw.investor_type)].filter(Boolean) as string[]
  };

  try {
    const { contactId } = await provider.createOrUpdateLead(lead, tenantId);
    // TODO: write audit row { tenant_id, action: 'lead_captured', target: contactId, created }
    return { ok: true, contactId, auditId: contactId };
  } catch (err) {
    return { ok: false, error: String(err) };
  }
}
