import { useState, useEffect, useCallback } from 'react';
import type { Deal } from '../types';

const DEALS_API = 'http://localhost:8766';
const POLL_INTERVAL = 60_000; // 60 seconds

interface UseDealsResult {
  deals: Deal[];
  loading: boolean;
  error: string | null;
  status: 'online' | 'offline' | 'loading';
  lastUpdated: Date | null;
  refresh: () => void;
}

export function useDeals(): UseDealsResult {
  const [deals, setDeals] = useState<Deal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<'online' | 'offline' | 'loading'>('loading');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchDeals = useCallback(async () => {
    try {
      setStatus('loading');
      const response = await fetch(`${DEALS_API}/deals`, {
        signal: AbortSignal.timeout(8000),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();

      // Handle both array and object responses
      const dealList: Deal[] = Array.isArray(data)
        ? data
        : data.deals ?? data.data ?? [];

      // Sort by overall_score desc
      const sorted = [...dealList].sort(
        (a, b) => (b.overall_score ?? 0) - (a.overall_score ?? 0)
      );

      setDeals(sorted);
      setError(null);
      setStatus('online');
      setLastUpdated(new Date());
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Unknown error';
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

  return { deals, loading, error, status, lastUpdated, refresh: fetchDeals };
}
