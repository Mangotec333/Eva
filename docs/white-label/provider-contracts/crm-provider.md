# CRMProvider Interface

> Provider-abstracted CRM contract. GHL is the default implementation; HubSpot/Pipedrive/Sheets implement the same contract. Swap & play.

## Interface (TypeScript-style pseudocode)

```typescript
interface CRMProvider {
  // Identity / health
  healthCheck(tenantId: string): Promise<{ ok: boolean; provider: string }>;

  // Leads / contacts
  createOrUpdateLead(input: LeadInput, tenantId: string): Promise<{ contactId: string; created: boolean }>;
  addTag(contactId: string, tag: string, tenantId: string): Promise<void>;
  updateContact(contactId: string, patch: Partial<LeadInput>, tenantId: string): Promise<void>;

  // Pipeline / deals
  createOpportunity(input: OpportunityInput, tenantId: string): Promise<{ opportunityId: string }>;
  moveOpportunity(opportunityId: string, stageId: string, tenantId: string): Promise<void>;

  // Campaigns / sequences
  enrollInCampaign(contactId: string, campaignId: string, tenantId: string): Promise<void>;

  // Introspection (used by OnboardingAgent)
  listCampaigns(tenantId: string): Promise<Campaign[]>;
  listPipelineStages(tenantId: string): Promise<Stage[]>;
}

interface LeadInput {
  name: string;
  email: string;
  phone?: string;
  company?: string;
  source?: string;
  tags?: string[];
  customFields?: Record<string, string>;
}
```

## Implementations
- **GHLProvider** — wraps `https://services.leadconnectorhq.com/contacts/` with `Authorization: Bearer <token>` + `Version: 2021-07-28`. Token from tenant credential vault (OAuth via Marketplace app; PIT only for prototype).
- **HubSpotProvider** — (future) same interface, HubSpot Contacts/Deals API.
- **PipedriveProvider** — (future).
- **SheetProvider** — (fallback) append to a per-tenant Google Sheet.

## Provider resolution
`TenantConfig.crm_provider` selects the implementation at runtime. All agents call the interface, never a vendor SDK directly.

## Notes
- Tokens never live in code or single-tenant env vars in production.
- Each call is scoped and logged with `tenant_id` for audit.
