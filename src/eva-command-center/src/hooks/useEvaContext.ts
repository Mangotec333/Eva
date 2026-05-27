import { useState, useEffect, useCallback } from 'react';
import type { EvaContextToday } from '../types';

const CONTEXT_API = 'http://localhost:8765';
const POLL_INTERVAL = 30_000; // 30 seconds

interface UseEvaContextResult {
  context: EvaContextToday | null;
  loading: boolean;
  error: string | null;
  status: 'online' | 'offline' | 'loading';
  lastUpdated: Date | null;
  refresh: () => void;
}

export function useEvaContext(): UseEvaContextResult {
  const [context, setContext] = useState<EvaContextToday | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<'online' | 'offline' | 'loading'>('loading');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchContext = useCallback(async () => {
    try {
      setStatus('loading');
      const response = await fetch(`${CONTEXT_API}/context/today`, {
        signal: AbortSignal.timeout(8000),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data: EvaContextToday = await response.json();
      setContext(data);
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
    fetchContext();
    const interval = setInterval(fetchContext, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchContext]);

  return { context, loading, error, status, lastUpdated, refresh: fetchContext };
}
