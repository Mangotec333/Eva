import { useState, useEffect, useCallback } from 'react';

const CONTENT_API = 'http://localhost:8767';
const POLL_INTERVAL = 60_000; // 60 seconds

// ─── Legacy types (preserved for ContentQueue component) ──────────────────────

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

// ─── LinkedIn Social Queue types ──────────────────────────────────────────────

export type PostVoice = 'operator' | 'builder' | 'thinker';
export type PostPillar = 'healthcare_real_estate' | 'ai_and_acquisition' | 'longevity_and_wealth';
export type PostStatus = 'draft' | 'approved' | 'posted' | 'failed';

export interface SocialPost {
  id: string;
  voice: PostVoice;
  pillar: PostPillar;
  main_post: string;
  comment_post?: string;
  status: PostStatus;
  char_count?: number;
  linkedin_url?: string;
  created_at: string;
  updated_at?: string;
}

export interface GeneratePostPayload {
  voice: PostVoice;
  pillar: PostPillar;
  topic_hint?: string;
}

export interface PostToLinkedInResult {
  success: boolean;
  linkedin_url?: string;
  error?: string;
}

export interface UseSocialQueueResult {
  posts: SocialPost[];
  isOnline: boolean;
  isLoading: boolean;
  linkedInConnected: boolean;
  generatePost: (voice: PostVoice, pillar: PostPillar, topicHint?: string) => Promise<SocialPost>;
  approvePost: (id: string) => Promise<void>;
  postToLinkedIn: (id: string) => Promise<PostToLinkedInResult>;
  enrichYoutube: (id: string) => Promise<void>;
  deletePost: (id: string) => Promise<void>;
  updatePost: (id: string, mainPost: string, commentPost: string) => Promise<void>;
  refresh: () => void;
}

export function useSocialQueue(): UseSocialQueueResult {
  const [posts, setPosts]                     = useState<SocialPost[]>([]);
  const [isOnline, setIsOnline]               = useState(false);
  const [isLoading, setIsLoading]             = useState(true);
  const [linkedInConnected, setLinkedInConnected] = useState(false);

  const fetchQueue = useCallback(async () => {
    try {
      setIsLoading(true);
      const res = await fetch(`${CONTENT_API}/content/queue`, {
        signal: AbortSignal.timeout(5000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const list: SocialPost[] = Array.isArray(data)
        ? data
        : data.posts ?? data.queue ?? data.drafts ?? [];
      setPosts(list);
      setIsOnline(true);
    } catch {
      setIsOnline(false);
      setPosts([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const fetchLinkedInStatus = useCallback(async () => {
    try {
      const res = await fetch(`${CONTENT_API}/content/linkedin/status`, {
        signal: AbortSignal.timeout(3000),
      });
      if (!res.ok) { setLinkedInConnected(false); return; }
      const data = await res.json();
      setLinkedInConnected(data.connected ?? false);
    } catch {
      setLinkedInConnected(false);
    }
  }, []);

  useEffect(() => {
    fetchQueue();
    fetchLinkedInStatus();
    const interval = setInterval(fetchQueue, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchQueue, fetchLinkedInStatus]);

  const generatePost = useCallback(
    async (voice: PostVoice, pillar: PostPillar, topicHint?: string): Promise<SocialPost> => {
      const payload: GeneratePostPayload = { voice, pillar };
      if (topicHint?.trim()) payload.topic_hint = topicHint.trim();
      const res = await fetch(`${CONTENT_API}/content/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(30_000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const post: SocialPost = await res.json();
      setPosts(prev => [post, ...prev]);
      return post;
    },
    []
  );

  const approvePost = useCallback(
    async (id: string) => {
      const res = await fetch(`${CONTENT_API}/content/approve/${id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setPosts(prev =>
        prev.map(p => (p.id === id ? { ...p, status: 'approved' as PostStatus } : p))
      );
    },
    []
  );

  const postToLinkedIn = useCallback(
    async (id: string): Promise<PostToLinkedInResult> => {
      const res = await fetch(`${CONTENT_API}/content/post/${id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: AbortSignal.timeout(30_000),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        return { success: false, error: errData.error ?? `HTTP ${res.status}` };
      }
      const data = await res.json();
      setPosts(prev =>
        prev.map(p =>
          p.id === id
            ? { ...p, status: 'posted' as PostStatus, linkedin_url: data.linkedin_url }
            : p
        )
      );
      return { success: true, linkedin_url: data.linkedin_url };
    },
    []
  );

  const enrichYoutube = useCallback(
    async (id: string) => {
      const res = await fetch(`${CONTENT_API}/content/youtube-enrich/${id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: AbortSignal.timeout(30_000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const updated: Partial<SocialPost> = await res.json();
      setPosts(prev =>
        prev.map(p => (p.id === id ? { ...p, ...updated } : p))
      );
    },
    []
  );

  const deletePost = useCallback(
    async (id: string) => {
      const res = await fetch(`${CONTENT_API}/content/draft/${id}`, {
        method: 'DELETE',
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setPosts(prev => prev.filter(p => p.id !== id));
    },
    []
  );

  const updatePost = useCallback(
    async (id: string, mainPost: string, commentPost: string) => {
      const res = await fetch(`${CONTENT_API}/content/draft/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ main_post: mainPost, comment_post: commentPost }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setPosts(prev =>
        prev.map(p =>
          p.id === id
            ? { ...p, main_post: mainPost, comment_post: commentPost, char_count: mainPost.length }
            : p
        )
      );
    },
    []
  );

  return {
    posts,
    isOnline,
    isLoading,
    linkedInConnected,
    generatePost,
    approvePost,
    postToLinkedIn,
    enrichYoutube,
    deletePost,
    updatePost,
    refresh: fetchQueue,
  };
}
