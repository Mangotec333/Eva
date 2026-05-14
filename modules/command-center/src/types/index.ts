// Deal Scout API types
export interface Deal {
  id: string | number;
  name: string;
  source: string;
  monthly_net: number;
  ai_proof_score: number;
  overall_score: number;
  status: 'PURSUING' | 'TRACKING' | 'PASSED' | string;
  net_after_heloc: number;
  asking_price?: number;
  multiple?: number;
  url?: string;
  notes?: string;
  listing_id?: string;
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
  | 'PROTECTED'
  | 'QUEUED'
  | 'BACKGROUND'
  | 'PAUSED';

export interface Priority {
  rank: number;
  name: string;
  status: PriorityStatus;
  description: string;
}

// Action Queue types
export type ActionTag = 'REVENUE' | 'BUILD' | 'ADMIN' | 'HEALTH' | 'REVIEW';

export interface Action {
  id: number;
  tag: ActionTag;
  text: string;
  url?: string;
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
