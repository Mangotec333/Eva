/**
 * CRMProvider interface — provider-abstracted CRM contract.
 * GHL is the default; HubSpot/Pipedrive/Sheet implement the same contract.
 *
 * See docs/white-label/provider-contracts/crm-provider.md
 */

export interface LeadInput {
  name: string;
  email: string;
  phone?: string;
  company?: string;
  source?: string;
  tags?: string[];
  customFields?: Record<string, string>;
}

export interface OpportunityInput {
  title: string;
  contactId: string;
  pipelineId?: string;
  stageId?: string;
  value?: number;
}

export interface Campaign {
  id: string;
  name: string;
}

export interface Stage {
  id: string;
  name: string;
  pipelineId: string;
}

export interface CRMProvider {
  readonly provider: string;
  healthCheck(tenantId: string): Promise<{ ok: boolean; provider: string }>;
  createOrUpdateLead(input: LeadInput, tenantId: string): Promise<{ contactId: string; created: boolean }>;
  addTag(contactId: string, tag: string, tenantId: string): Promise<void>;
  updateContact(contactId: string, patch: Partial<LeadInput>, tenantId: string): Promise<void>;
  createOpportunity(input: OpportunityInput, tenantId: string): Promise<{ opportunityId: string }>;
  moveOpportunity(opportunityId: string, stageId: string, tenantId: string): Promise<void>;
  enrollInCampaign(contactId: string, campaignId: string, tenantId: string): Promise<void>;
  listCampaigns(tenantId: string): Promise<Campaign[]>;
  listPipelineStages(tenantId: string): Promise<Stage[]>;
}
