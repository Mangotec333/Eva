import { useState, useEffect, useCallback } from 'react';
import type { Deal, DealHistory } from '../types';

const DEALS_API = 'http://localhost:8766';
const POLL_INTERVAL = 60_000; // 60 seconds

// Pipeline response: { [stage]: Deal[] }
type PipelineResponse = Record<string, Deal[]>;

interface UseDealsResult {
  pipelineDeals: PipelineResponse;
  archivedDeals: Deal[];
  allDeals: Deal[];
  deals: Deal[]; // backward compat alias for allDeals
  loading: boolean;
  error: string | null;
  status: 'online' | 'offline' | 'loading';
  lastUpdated: Date | null;
  refresh: () => void;
  advanceStage: (id: string, stage: string, reason: string) => Promise<void>;
  archiveDeal: (id: string, reason: string) => Promise<void>;
  unarchiveDeal: (id: string) => Promise<void>;
  getDealHistory: (id: string) => Promise<DealHistory[]>;
}

export function useDeals(): UseDealsResult {
  const [pipelineDeals, setPipelineDeals] = useState<PipelineResponse>({});
  const [archivedDeals, setArchivedDeals] = useState<Deal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<'online' | 'offline' | 'loading'>('loading');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchDeals = useCallback(async () => {
    try {
      setStatus('loading');

      const [pipelineRes, archivedRes] = await Promise.all([
        fetch(`${DEALS_API}/deals/pipeline`, { signal: AbortSignal.timeout(8000) }),
        fetch(`${DEALS_API}/deals/archived`, { signal: AbortSignal.timeout(8000) }),
      ]);

      if (!pipelineRes.ok) {
        throw new Error(`Pipeline HTTP ${pipelineRes.status}: ${pipelineRes.statusText}`);
      }

      const pipelineData: PipelineResponse = await pipelineRes.json();
      setPipelineDeals(pipelineData);

      if (archivedRes.ok) {
        const archivedData = await archivedRes.json();
        const list: Deal[] = Array.isArray(archivedData)
          ? archivedData
          : archivedData.deals ?? archivedData.data ?? [];
        setArchivedDeals(list);
      }

      setError(null);
      setStatus('online');
      setLastUpdated(new Date());
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      setStatus('offline');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDeals();
    const interval = setInterval(fetchDeals, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchDeals]);

  const advanceStage = useCallback(
    async (id: string, stage: string, reason: string) => {
      const res = await fetch(`${DEALS_API}/deals/${id}/stage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stage, reason }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchDeals();
    },
    [fetchDeals]
  );

  const archiveDeal = useCallback(
    async (id: string, reason: string) => {
      const res = await fetch(`${DEALS_API}/deals/${id}/archive`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchDeals();
    },
    [fetchDeals]
  );

  const unarchiveDeal = useCallback(
    async (id: string) => {
      const res = await fetch(`${DEALS_API}/deals/${id}/unarchive`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchDeals();
    },
    [fetchDeals]
  );

  const getDealHistory = useCallback(async (id: string): Promise<DealHistory[]> => {
    const res = await fetch(`${DEALS_API}/deals/${id}/history`, {
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return Array.isArray(data) ? data : data.history ?? [];
  }, []);

  // Flatten all pipeline stages into one array (sorted by overall_score desc)
  const allDeals: Deal[] = Object.values(pipelineDeals)
    .flat()
    .sort((a, b) => (b.overall_score ?? 0) - (a.overall_score ?? 0));

  return {
    pipelineDeals,
    archivedDeals,
    allDeals,
    deals: allDeals, // backward-compat
    loading,
    error,
    status,
    lastUpdated,
    refresh: fetchDeals,
    advanceStage,
    archiveDeal,
    unarchiveDeal,
    getDealHistory,
  };
}
