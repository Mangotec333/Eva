// Deal Scout API types — v2
export interface Deal {
  id: string;
  source: string;
  listing_id: string;
  url: string;
  name: string;
  category: string;
  monthly_net: number;
  annual_multiple: number;
  asking_price: number;
  age_years: number;
  stage: string;           // renamed from status
  market_status: string;   // "available" | "sold" | "off_market"
  is_archived: boolean;
  archive_reason: string;
  archived_at: string;
  buy_vs_build_decision: string;  // "buy" | "build" | "hybrid"
  buy_vs_build_score: number;
  buy_vs_build_reason: string;
  notes: string;
  cashflow_score: number;
  moat_score: number;
  ai_proof_score: number;
  value_add_score: number;
  risk_score: number;
  overall_score: number;
  down_payment: number;
  seller_finance_amount: number;
  monthly_debt_service: number;
  net_monthly_cashflow: number;
  heloc_used: number;
  heloc_interest_monthly: number;
  net_after_heloc: number;
  discovered_at: string;
  stage_changed_at: string;
  created_at: string;
  updated_at: string;
}

export interface DealHistory {
  id: string;
  deal_id: string;
  event_type: string;
  from_value: string;
  to_value: string;
  field_name: string;
  reason: string;
  note: string;
  created_at: string;
}

export interface DealsResponse {
  deals: Deal[];
  total?: number;
  updated_at?: string;
}

// EVA Context API types
export interface ContextActivity {
  id: string | number;
  timestamp: string;
  type: string;
  summary: string;
  source?: string;
  metadata?: Record<string, unknown>;
}

export interface EvaContextToday {
  date: string;
  activities: ContextActivity[];
  summary?: string;
  focus?: string;
  energy_level?: number;
  sessions?: number;
  last_updated?: string;
}

// Priority types
export type PriorityStatus =
  | 'ACTIVE - BUILDING'
  | '90-DAY TARGET'
  | 'FLYWHEEL'
  | 'PROTECTED'
  | 'QUEUED'
  | 'BACKGROUND'
  | 'PAUSED';

export interface Priority {
  rank: number;
  name: string;
  track: string;          // short track label e.g. "EVA OS"
  status: PriorityStatus;
  description: string;
  metric?: string;        // key metric to show e.g. "$0 / $10K"
  flywheel?: boolean;     // marks tracks that feed the flywheel
}

// Action Queue types
export type ActionTag = 'REVENUE' | 'BUILD' | 'ADMIN' | 'HEALTH' | 'REVIEW';

export interface Action {
  id: number;
  tag: ActionTag;
  text: string;
  url?: string;
  command?: string;
  completed: boolean;
}

// Energy Budget types
export interface EnergyBucket {
  label: string;
  percentage: number;
  color: string;
}

// API status
export interface ApiStatus {
  dealScout: 'online' | 'offline' | 'loading';
  evaContext: 'online' | 'offline' | 'loading';
}
