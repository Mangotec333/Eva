import { useState, useEffect, useCallback } from 'react';
import { ExternalLink, RefreshCw, Plus, ChevronDown } from 'lucide-react';

// ─── Types ─────────────────────────────────────────────────────────────────────

interface Experiment {
  name: string;
  startedAt: string;
  endsAt: string;
  status: 'running' | 'ended';
  winner: 'A' | 'B' | null;
}

interface PostMetrics {
  id: string;
  url: string;
  hook: string;
  keyword: string;
  audience: string;
  tagged?: string;
  reactions: number;
  comments: number;
  reposts: number;
  keywordHits: number;
}

type ActionTaken = 'none' | 'Replied' | 'Sent DM' | 'Ignored' | 'Added to waitlist';

interface SignalItem {
  id: string;
  commenter: string;
  platform: string;
  content: string;
  keyword: string;
  timestamp: string;
  action: ActionTaken;
}

// ─── Helpers ───────────────────────────────────────────────────────────────────

function timeAgo(ts: string): string {
  const diff  = Date.now() - new Date(ts).getTime();
  const mins  = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days  = Math.floor(diff / 86400000);
  if (mins  < 1)  return 'just now';
  if (mins  < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  return `${days}d ago`;
}

function experimentProgress(startedAt: string, endsAt: string): number {
  const start   = new Date(startedAt).getTime();
  const end     = new Date(endsAt).getTime();
  const now     = Date.now();
  const total   = end - start;
  const elapsed = Math.max(0, Math.min(now - start, total));
  return total > 0 ? (elapsed / total) * 100 : 0;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day:   'numeric',
    hour:  'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

// ─── Section 1: Experiment Banner ─────────────────────────────────────────────

function ExperimentBanner({ experiment }: { experiment: Experiment }) {
  const progress = experimentProgress(experiment.startedAt, experiment.endsAt);
  const isOver   = progress >= 100;

  return (
    <div className="bg-[#111] border border-[#00ff88]/20 rounded-lg px-5 py-4">
      {/* Top row */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1.5 min-w-0">
          {/* Pill */}
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 bg-[#00ff88]/10 border border-[#00ff88]/30 rounded-full font-mono text-[10px] font-bold text-[#00ff88] tracking-widest uppercase">
              <span className={`w-1.5 h-1.5 rounded-full bg-[#00ff88] ${!isOver ? 'animate-pulse' : ''}`} />
              {isOver ? 'Experiment Ended' : 'Experiment Running'}
            </span>
          </div>
          {/* Title */}
          <div className="font-mono text-sm font-bold text-gray-900 tracking-tight">
            {experiment.name}
          </div>
          {/* Subtitle */}
          <div className="font-mono text-[11px] text-gray-500">
            Posted May 19 · 48hr window · Ends {formatDate(experiment.endsAt)}
          </div>
        </div>

        {/* Right: prize */}
        <div className="shrink-0 text-right">
          <div className="font-mono text-[10px] text-gray-500 uppercase tracking-widest mb-0.5">Winner Gets</div>
          <div className="font-mono text-sm font-bold text-[#00ff88]">$200 ad spend</div>
        </div>
      </div>

      {/* Progress bar */}
      <div className="mt-4">
        <div className="flex justify-between mb-1.5">
          <span className="font-mono text-[10px] text-gray-500">Time elapsed</span>
          <span className="font-mono text-[10px] text-gray-500">{Math.round(progress)}%</span>
        </div>
        <div className="h-1.5 bg-[#0a0a0a] rounded-full border border-[#1a1a1a] overflow-hidden">
          <div
            className="h-full rounded-full bg-[#00ff88] transition-all duration-500"
            style={{ width: `${progress}%`, opacity: isOver ? 0.5 : 1 }}
          />
        </div>
      </div>
    </div>
  );
}

// ─── Section 2: Post Cards ─────────────────────────────────────────────────────

type PostStatus = 'RUNNING' | 'WIN' | 'LOSE';

function PostCard({
  label,
  post,
  status,
}: {
  label: 'A' | 'B';
  post: PostMetrics;
  status: PostStatus;
}) {
  const statusCfg = {
    RUNNING: { bg: 'bg-amber-500/10',   border: 'border-amber-500/30',   text: 'text-amber-400'  },
    WIN:     { bg: 'bg-[#00ff88]/10',   border: 'border-[#00ff88]/30',   text: 'text-[#00ff88]'  },
    LOSE:    { bg: 'bg-red-500/10',     border: 'border-red-500/30',     text: 'text-red-400'    },
  }[status];

  return (
    <div className="flex-1 bg-[#111] border border-[#1a1a1a] rounded-lg p-4 flex flex-col gap-3 min-w-0">
      {/* Header row */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-mono text-[10px] text-gray-500 uppercase tracking-widest shrink-0">
            Test {label}
          </span>
          <span className="font-mono text-[10px] text-gray-500 truncate">· {post.audience}</span>
        </div>
        {/* Status badge */}
        <span className={`shrink-0 inline-block px-2 py-0.5 border rounded font-mono text-[9px] font-bold tracking-widest uppercase ${statusCfg.bg} ${statusCfg.border} ${statusCfg.text}`}>
          {status}
        </span>
      </div>

      {/* Hook */}
      <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded px-3 py-2.5">
        <p className="font-sans text-xs text-gray-500 leading-relaxed italic">"{post.hook}"</p>
      </div>

      {/* Keyword CTA */}
      <div className="flex items-center gap-2">
        <span className="font-mono text-[10px] text-gray-500 uppercase tracking-widest">Keyword CTA:</span>
        <span className="px-2 py-0.5 bg-[#00ff88]/10 border border-[#00ff88]/30 rounded font-mono text-[10px] font-bold text-[#00ff88] tracking-wider">
          {post.keyword}
        </span>
        {post.tagged && (
          <span className="px-2 py-0.5 bg-purple-500/15 border border-purple-500/30 rounded font-mono text-[10px] font-bold text-purple-400">
            {post.tagged}
          </span>
        )}
      </div>

      {/* Metrics row */}
      <div className="grid grid-cols-3 gap-2">
        {[
          { label: 'Reactions', value: post.reactions },
          { label: 'Comments',  value: post.comments  },
          { label: 'Reposts',   value: post.reposts   },
        ].map(m => (
          <div key={m.label} className="bg-[#0a0a0a] border border-[#1a1a1a] rounded px-2.5 py-2 text-center">
            <div className="font-mono text-sm font-bold text-gray-800 tabular-nums">{m.value}</div>
            <div className="font-mono text-[9px] text-gray-500 uppercase tracking-widest mt-0.5">{m.label}</div>
          </div>
        ))}
      </div>

      {/* Keyword hits */}
      <div className="flex items-center justify-between">
        <span className="font-mono text-[10px] text-gray-500 uppercase tracking-widest">Keyword Hits</span>
        <span className={`font-mono text-2xl font-bold tabular-nums ${post.keywordHits > 0 ? 'text-[#00ff88]' : 'text-gray-500'}`}>
          {post.keywordHits}
        </span>
      </div>

      {/* View post link */}
      <a
        href={post.url}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center gap-1.5 font-mono text-[11px] text-gray-500 hover:text-[#00ff88] transition-colors group mt-auto"
      >
        <ExternalLink className="w-3 h-3 group-hover:text-[#00ff88]" />
        View Post →
      </a>
    </div>
  );
}

// ─── Section 3: Signal Feed ────────────────────────────────────────────────────

const ACTION_OPTIONS: ActionTaken[] = ['none', 'Replied', 'Sent DM', 'Ignored', 'Added to waitlist'];

function SignalRow({
  signal,
  onActionChange,
}: {
  signal: SignalItem;
  onActionChange: (id: string, action: ActionTaken) => void;
}) {
  return (
    <div className="bg-[#111] border border-[#1a1a1a] rounded-lg px-4 py-3 flex flex-col gap-2 hover:border-gray-200 transition-colors">
      {/* Top: name + platform + timestamp */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-mono text-xs font-semibold text-gray-800 truncate">{signal.commenter}</span>
          <span className="font-mono text-[10px] text-gray-500 shrink-0">· {signal.platform}</span>
        </div>
        <span className="font-mono text-[10px] text-gray-400 shrink-0">{timeAgo(signal.timestamp)}</span>
      </div>

      {/* Content */}
      <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded px-2.5 py-2 font-sans text-xs text-gray-500 leading-relaxed">
        {signal.content}
      </div>

      {/* Bottom: keyword pill + action dropdown */}
      <div className="flex items-center justify-between gap-2">
        <span className="px-2 py-0.5 bg-[#00ff88]/10 border border-[#00ff88]/30 rounded font-mono text-[10px] font-bold text-[#00ff88] tracking-wider">
          {signal.keyword}
        </span>
        <div className="relative flex items-center gap-1">
          <select
            value={signal.action}
            onChange={e => onActionChange(signal.id, e.target.value as ActionTaken)}
            className="appearance-none bg-[#0a0a0a] border border-[#1a1a1a] rounded px-2.5 py-1 pr-6 font-mono text-[10px] text-gray-500 focus:outline-none focus:border-[#00ff88]/40 cursor-pointer hover:border-gray-200 transition-colors"
          >
            {ACTION_OPTIONS.map(opt => (
              <option key={opt} value={opt}>
                {opt === 'none' ? 'Action Taken…' : opt}
              </option>
            ))}
          </select>
          <ChevronDown className="w-3 h-3 text-gray-500 absolute right-1.5 pointer-events-none" />
        </div>
      </div>
    </div>
  );
}

function SignalFeedSection({
  signals,
  onActionChange,
}: {
  signals: SignalItem[];
  onActionChange: (id: string, action: ActionTaken) => void;
}) {
  return (
    <div className="bg-[#111] border border-[#1a1a1a] rounded-lg p-4 flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="font-mono text-[10px] text-gray-500 uppercase tracking-widest">Live Signals</span>
        <span className="font-mono text-[10px] text-gray-400">Polling every 30m</span>
      </div>

      {/* Signal list */}
      {signals.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-8 gap-2 bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg">
          <span className="font-mono text-xs text-gray-500 text-center leading-relaxed">
            No keyword signals yet — checking every 30 minutes
          </span>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {signals.map(sig => (
            <SignalRow key={sig.id} signal={sig} onActionChange={onActionChange} />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Section 4: Pattern Mining ─────────────────────────────────────────────────

const SEED_LEARNINGS = [
  'Public CTA outperforms DM ask (algorithm amplification)',
  'Alex Hormozi tag = credibility signal regardless of engagement',
];

function PatternMining() {
  const [learnings, setLearnings] = useState<string[]>(SEED_LEARNINGS);
  const [newLearning, setNewLearning]   = useState('');
  const [adding, setAdding]             = useState(false);

  const handleAdd = useCallback(() => {
    const trimmed = newLearning.trim();
    if (!trimmed) return;
    setLearnings(prev => [...prev, trimmed]);
    setNewLearning('');
    setAdding(false);
  }, [newLearning]);

  return (
    <div className="bg-[#111] border border-[#1a1a1a] rounded-lg p-4 flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="font-mono text-[10px] text-gray-500 uppercase tracking-widest">What's Working</span>
        <button
          onClick={() => setAdding(v => !v)}
          className="flex items-center gap-1 px-2 py-1 bg-[#00ff88]/10 border border-[#00ff88]/30 text-[#00ff88] rounded font-mono text-[10px] font-bold hover:bg-[#00ff88]/20 active:scale-95 transition-all cursor-pointer"
        >
          <Plus className="w-3 h-3" />
          Add Learning
        </button>
      </div>

      {/* Learnings list */}
      <ul className="flex flex-col gap-1.5">
        {learnings.map((l, i) => (
          <li key={i} className="flex items-start gap-2 font-sans text-xs text-gray-500 leading-relaxed">
            <span className="text-[#00ff88] shrink-0 mt-0.5 font-bold">•</span>
            <span>{l}</span>
          </li>
        ))}
      </ul>

      {/* Add learning input */}
      {adding && (
        <div className="flex gap-2 mt-1">
          <input
            type="text"
            value={newLearning}
            onChange={e => setNewLearning(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleAdd(); if (e.key === 'Escape') { setAdding(false); setNewLearning(''); } }}
            placeholder="Log a new learning…"
            autoFocus
            className="flex-1 bg-[#0a0a0a] border border-[#1a1a1a] rounded px-3 py-1.5 font-mono text-xs text-gray-500 placeholder:text-gray-400 focus:outline-none focus:border-[#00ff88]/40 transition-colors"
          />
          <button
            onClick={handleAdd}
            disabled={!newLearning.trim()}
            className="px-3 py-1.5 bg-[#00ff88]/15 border border-[#00ff88]/40 text-[#00ff88] rounded font-mono text-xs font-bold hover:bg-[#00ff88]/25 disabled:opacity-40 disabled:cursor-not-allowed active:scale-95 transition-all cursor-pointer"
          >
            Save
          </button>
        </div>
      )}
    </div>
  );
}

// ─── Main Component ────────────────────────────────────────────────────────────

const SIGNALS_API  = 'http://localhost:8770';
const CONTENT_API  = 'http://localhost:8767';
const POLL_MS      = 5 * 60 * 1000; // 5 minutes

export function SocialSignals() {
  // Experiment window: live for 7 days from component first mount
  const [experiment, setExperiment] = useState<Experiment>(() => {
    const savedStart = localStorage.getItem('eva_exp_startedAt');
    const start = savedStart ?? new Date('2026-05-19T11:48:00-07:00').toISOString();
    if (!savedStart) {
      // First time — persist so the window doesn't reset on re-render
      try { localStorage.setItem('eva_exp_startedAt', start); } catch {}
    }
    const startMs  = new Date(start).getTime();
    const endsAt   = new Date(startMs + 7 * 24 * 60 * 60 * 1000).toISOString();
    const isOver   = Date.now() >= new Date(endsAt).getTime();
    return {
      name:      'LinkedIn Audience Validation — SCOUT vs OPERATOR',
      startedAt: start,
      endsAt,
      status:    isOver ? 'ended' : 'running',
      winner:    null,
    };
  });

  const [postA, setPostA] = useState<PostMetrics>({
    id:          'li_7462573426755506176',
    url:         'https://www.linkedin.com/posts/activity-7462573426755506176-4p8l',
    hook:        'Grata charges $100K/year — I built it for $0',
    keyword:     'SCOUT',
    audience:    'Acquisition Entrepreneurs',
    reactions:   0,
    comments:    0,
    reposts:     0,
    keywordHits: 0,
  });

  const [postB, setPostB] = useState<PostMetrics>({
    id:          'li_7462572485633380353',
    url:         'https://www.linkedin.com/posts/activity-7462572485633380353-tGGa',
    hook:        'RCFE is a paper problem disguised as a care problem',
    keyword:     'OPERATOR',
    audience:    'RCFE Operators',
    tagged:      'Alex Hormozi',
    reactions:   0,
    comments:    0,
    reposts:     0,
    keywordHits: 0,
  });

  const [signals,     setSignals]     = useState<SignalItem[]>([]);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [refreshing,  setRefreshing]  = useState(false);

  // ── Determine winner from live metrics ──────────────────────────────────────
  function resolveStatus(post: PostMetrics, other: PostMetrics): PostStatus {
    if (experiment.winner === 'A' && post.id === postA.id) return 'WIN';
    if (experiment.winner === 'B' && post.id === postB.id) return 'WIN';
    if (experiment.winner !== null) return 'LOSE';
    if (experiment.status === 'ended') {
      const scoreA = postA.keywordHits * 3 + postA.reactions + postA.comments * 2;
      const scoreB = postB.keywordHits * 3 + postB.reactions + postB.comments * 2;
      if (post.id === postA.id) return scoreA >= scoreB ? 'WIN' : 'LOSE';
      return scoreB > scoreA ? 'WIN' : 'LOSE';
    }
    return 'RUNNING';
  }

  // ── Fetch signals ──────────────────────────────────────────────────────────
  const fetchSignals = useCallback(async () => {
    try {
      const r = await fetch(`${SIGNALS_API}/channels/signal`, {
        signal: AbortSignal.timeout(5000),
      });
      if (!r.ok) return;
      const data = await r.json();
      const raw: SignalItem[] = (Array.isArray(data) ? data : data.signals ?? []).map((s: {
        id?: string;
        commenter?: string;
        author?: string;
        platform?: string;
        content?: string;
        keyword?: string;
        timestamp?: string;
        action?: ActionTaken;
      }) => ({
        id:        s.id        ?? `sig-${Math.random().toString(36).slice(2)}`,
        commenter: s.commenter ?? s.author ?? 'Unknown',
        platform:  s.platform  ?? 'LinkedIn',
        content:   s.content   ?? '',
        keyword:   s.keyword   ?? '',
        timestamp: s.timestamp ?? new Date().toISOString(),
        action:    s.action    ?? 'none',
      }));
      setSignals(raw);
    } catch {
      // silent fail — keep existing signals
    }
  }, []);

  // ── Fetch post metrics ─────────────────────────────────────────────────────
  const fetchPostMetrics = useCallback(async () => {
    try {
      const r = await fetch(`${CONTENT_API}/content/posts`, {
        signal: AbortSignal.timeout(5000),
      });
      if (!r.ok) return;
      const data = await r.json();
      const posts: {
        id?: string;
        reactions?: number;
        comments?: number;
        reposts?: number;
        keyword_hits?: number;
        keywordHits?: number;
        status?: string;
        winner?: 'A' | 'B' | null;
      }[] = Array.isArray(data) ? data : data.posts ?? [];

      posts.forEach(p => {
        const updater = (prev: PostMetrics): PostMetrics => ({
          ...prev,
          reactions:   typeof p.reactions    === 'number' ? p.reactions    : prev.reactions,
          comments:    typeof p.comments     === 'number' ? p.comments     : prev.comments,
          reposts:     typeof p.reposts      === 'number' ? p.reposts      : prev.reposts,
          keywordHits: typeof p.keyword_hits === 'number' ? p.keyword_hits
                     : typeof p.keywordHits  === 'number' ? p.keywordHits  : prev.keywordHits,
        });
        if (p.id === postA.id) setPostA(updater);
        if (p.id === postB.id) setPostB(updater);
      });

      // Check if the API is also reporting a winner
      const meta = Array.isArray(data) ? null : data;
      if (meta?.winner) {
        setExperiment(prev => ({ ...prev, winner: meta.winner, status: 'ended' }));
      }
    } catch {
      // silent fail — keep seeded data
    }
  }, [postA.id, postB.id]);

  // ── Refresh everything ─────────────────────────────────────────────────────
  const refresh = useCallback(async () => {
    setRefreshing(true);
    await Promise.all([fetchSignals(), fetchPostMetrics()]);
    setLastRefresh(new Date());
    setRefreshing(false);
  }, [fetchSignals, fetchPostMetrics]);

  // ── Mount + poll ───────────────────────────────────────────────────────────
  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  // ── Signal action handler ──────────────────────────────────────────────────
  const handleActionChange = useCallback((id: string, action: ActionTaken) => {
    setSignals(prev => prev.map(s => s.id === id ? { ...s, action } : s));
  }, []);

  const statusA = resolveStatus(postA, postB);
  const statusB = resolveStatus(postB, postA);

  return (
    <div className="flex flex-col gap-4">
      {/* Panel header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] text-gray-500 uppercase tracking-widest">Social Signals</span>
          <span className="w-1.5 h-1.5 rounded-full bg-[#00ff88] animate-pulse" />
        </div>
        <div className="flex items-center gap-2">
          {lastRefresh && (
            <span className="font-mono text-[10px] text-gray-400">
              Updated {timeAgo(lastRefresh.toISOString())}
            </span>
          )}
          <button
            onClick={refresh}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-2.5 py-1 bg-[#111] border border-[#1a1a1a] text-gray-500 rounded font-mono text-[10px] hover:border-gray-200 hover:text-gray-500 disabled:opacity-40 active:scale-95 transition-all cursor-pointer"
          >
            <RefreshCw className={`w-3 h-3 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Section 1: Experiment Banner */}
      <ExperimentBanner experiment={experiment} />

      {/* Section 2: Post Performance */}
      <div>
        <div className="font-mono text-[10px] text-gray-500 uppercase tracking-widest mb-3">
          Post Performance
        </div>
        <div className="flex gap-4">
          <PostCard label="A" post={postA} status={statusA} />
          <PostCard label="B" post={postB} status={statusB} />
        </div>
      </div>

      {/* Section 3: Signal Feed */}
      <SignalFeedSection signals={signals} onActionChange={handleActionChange} />

      {/* Section 4: Pattern Mining */}
      <PatternMining />
    </div>
  );
}
