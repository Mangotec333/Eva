import { useState, useEffect, useCallback } from 'react';

const CONTENT_API = 'http://localhost:8767';
const POLL_INTERVAL = 60_000; // 60 seconds

export interface ContentDraft {
  id: string;
  content_type: 'thought_leader' | 'builder_log' | 'human_story' | 'teach';
  hook: string;
  draft_text: string;
  hashtags: string[];
  reach_estimate: 'HIGH' | 'MEDIUM' | 'LOW';
  platform?: string;
  created_at: string;
  status?: 'pending' | 'approved' | 'rejected';
}

interface UseContentQueueResult {
  drafts: ContentDraft[];
  isOnline: boolean;
  isLoading: boolean;
  approveDraft: (id: string) => Promise<void>;
  rejectDraft: (id: string, reason: string) => Promise<void>;
  approveAll: () => Promise<void>;
  editDraft: (id: string, draft_text: string) => Promise<void>;
  generateNow: () => Promise<void>;
  refresh: () => void;
}

export function useContentQueue(): UseContentQueueResult {
  const [drafts, setDrafts] = useState<ContentDraft[]>([]);
  const [isOnline, setIsOnline] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  const fetchQueue = useCallback(async () => {
    try {
      setIsLoading(true);
      const res = await fetch(`${CONTENT_API}/drafts/queue`, {
        signal: AbortSignal.timeout(5000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const list: ContentDraft[] = Array.isArray(data)
        ? data
        : data.drafts ?? data.queue ?? [];
      setDrafts(list);
      setIsOnline(true);
    } catch {
      setIsOnline(false);
      setDrafts([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchQueue();
    const interval = setInterval(fetchQueue, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchQueue]);

  const approveDraft = useCallback(
    async (id: string) => {
      const res = await fetch(`${CONTENT_API}/drafts/${id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setDrafts(prev => prev.filter(d => d.id !== id));
    },
    []
  );

  const rejectDraft = useCallback(
    async (id: string, reason: string) => {
      const res = await fetch(`${CONTENT_API}/drafts/${id}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setDrafts(prev => prev.filter(d => d.id !== id));
    },
    []
  );

  const approveAll = useCallback(
    async () => {
      const ids = drafts.map(d => d.id);
      const res = await fetch(`${CONTENT_API}/drafts/approve-batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setDrafts([]);
    },
    [drafts]
  );

  const editDraft = useCallback(
    async (id: string, draft_text: string) => {
      const res = await fetch(`${CONTENT_API}/drafts/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ draft_text }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setDrafts(prev =>
        prev.map(d => (d.id === id ? { ...d, draft_text } : d))
      );
    },
    []
  );

  const generateNow = useCallback(async () => {
    const res = await fetch(`${CONTENT_API}/drafts/generate-from-eva`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    await fetchQueue();
  }, [fetchQueue]);

  return {
    drafts,
    isOnline,
    isLoading,
    approveDraft,
    rejectDraft,
    approveAll,
    editDraft,
    generateNow,
    refresh: fetchQueue,
  };
}
