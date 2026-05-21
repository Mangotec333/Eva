import { useState, useEffect, useCallback } from 'react';
import { ExternalLink, Loader2, RefreshCw, TrendingUp, DollarSign, BarChart2, Zap } from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────

type Stage = 'nda_signed' | 'in_progress' | 'tracking' | 'closed' | 'passed';
type Decision = 'BUY' | 'PASS' | 'WATCH' | 'REVIEW';
type SortKey = 'score' | 'net_mo' | 'multiple' | 'ai_proof';
type CategoryTab = 'online' | 'healthcare' | 'high_potential';

interface Deal {
  id: string;
  name: string;
  source: string;
  source_badge: string;
  url: string;
  net_mo: number;
  asking: number;
  multiple: number;
  ai_proof: number;
  eva_score: number;
  net_after_heloc: number;
  stage: Stage;
  age_yr: number;
  decision: Decision;
  category: 'online' | 'healthcare' | 'high_potential';
}

// ─── Seed Data ────────────────────────────────────────────────────────────────

const SEED_DEALS: Deal[] = [
  {
    id: 'ef-87872',
    name: 'EF #87872 Digital Media Services',
    source: 'Empire Flippers',
    source_badge: 'EF',
    url: 'https://empireflippers.com/listing/87872',
    net_mo: 11478,
    asking: 261414,
    multiple: 1.9,
    ai_proof: 84,
    eva_score: 7.78,
    net_after_heloc: 6923,
    stage: 'nda_signed',
    age_yr: 6,
    decision: 'BUY',
    category: 'online',
  },
  {
    id: 'flippa-12032980',
    name: 'Flippa #12032980 Real Estate Comparison',
    source: 'Flippa',
    source_badge: 'Flippa',
    url: 'https://flippa.com/listing/12032980',
    net_mo: 13500,
    asking: 259200,
    multiple: 1.6,
    ai_proof: 68,
    eva_score: 7.15,
    net_after_heloc: 8984,
    stage: 'tracking',
    age_yr: 5,
    decision: 'BUY',
    category: 'online',
  },
  {
    id: 'flippa-12278661',
    name: 'Flippa #12278661 WordPress Plugin 13yr',
    source: 'Flippa',
    source_badge: 'Flippa',
    url: 'https://flippa.com/listing/12278661',
    net_mo: 7581,
    asking: 273916,
    multiple: 3.0,
    ai_proof: 61,
    eva_score: 6.94,
    net_after_heloc: 2808,
    stage: 'tracking',
    age_yr: 13,
    decision: 'BUY',
    category: 'online',
  },
  {
    id: 'flippa-12166327',
    name: 'Flippa #12166327 Education Tutoring',
    source: 'Flippa',
    source_badge: 'Flippa',
    url: 'https://flippa.com/listing/12166327',
    net_mo: 7195,
    asking: 155412,
    multiple: 1.8,
    ai_proof: 82,
    eva_score: 6.77,
    net_after_heloc: 4487,
    stage: 'in_progress',
    age_yr: 6,
    decision: 'BUY',
    category: 'online',
  },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmt$(n: number): string {
  return '$' + n.toLocaleString('en-US');
}

function fmtK(n: number): string {
  if (n >= 1000) return '$' + (n / 1000).toFixed(0) + 'K';
  return fmt$(n);
}

// ─── Stage Badge ──────────────────────────────────────────────────────────────

const STAGE_CONFIG: Record<Stage, { label: string; bg: string; text: string; border: string }> = {
  nda_signed:  { label: 'NDA Signed',  bg: 'bg-purple-500/15', text: 'text-purple-400', border: 'border-purple-500/30' },
  in_progress: { label: 'In Progress', bg: 'bg-blue-500/15',   text: 'text-blue-400',   border: 'border-blue-500/30'   },
  tracking:    { label: 'Tracking',    bg: 'bg-gray-500/15',   text: 'text-gray-400',   border: 'border-gray-600/30'   },
  closed:      { label: 'Closed',      bg: 'bg-green-500/15',  text: 'text-green-400',  border: 'border-green-500/30'  },
  passed:      { label: 'Passed',      bg: 'bg-red-500/15',    text: 'text-red-400',    border: 'border-red-500/30'    },
};

function StageBadge({ stage }: { stage: Stage }) {
  const cfg = STAGE_CONFIG[stage];
  return (
    <span className={`px-1.5 py-0.5 rounded border font-mono text-[9px] font-bold tracking-wider uppercase ${cfg.bg} ${cfg.text} ${cfg.border}`}>
      {cfg.label}
    </span>
  );
}

// ─── Source Badge ─────────────────────────────────────────────────────────────

function SourceBadge({ badge }: { badge: string }) {
  const isEF = badge === 'EF';
  return (
    <span className={`px-1.5 py-0.5 rounded border font-mono text-[9px] font-bold tracking-wider ${
      isEF
        ? 'bg-amber-500/15 text-amber-400 border-amber-500/30'
        : 'bg-sky-500/15 text-sky-400 border-sky-500/30'
    }`}>
      {badge}
    </span>
  );
}

// ─── Decision Badge ───────────────────────────────────────────────────────────

const DECISION_CONFIG: Record<Decision, { bg: string; text: string; border: string }> = {
  BUY:    { bg: 'bg-[#00ff88]/15', text: 'text-[#00ff88]', border: 'border-[#00ff88]/30' },
  WATCH:  { bg: 'bg-yellow-500/15', text: 'text-yellow-400', border: 'border-yellow-500/30' },
  PASS:   { bg: 'bg-red-500/15',    text: 'text-red-400',    border: 'border-red-500/30'    },
  REVIEW: { bg: 'bg-blue-500/15',   text: 'text-blue-400',   border: 'border-blue-500/30'   },
};

function DecisionBadge({ decision }: { decision: Decision }) {
  const cfg = DECISION_CONFIG[decision];
  return (
    <span className={`px-2 py-0.5 rounded border font-mono text-[10px] font-bold tracking-wider ${cfg.bg} ${cfg.text} ${cfg.border}`}>
      {decision}
    </span>
  );
}

// ─── AI-Proof Score Bar ───────────────────────────────────────────────────────

function AIProofBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.max(0, score));
  const color = score >= 75 ? '#00ff88' : score >= 60 ? '#facc15' : '#f87171';

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-[#0a0a0a] rounded-full overflow-hidden border border-[#1a1a1a]">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="font-mono text-[10px] tabular-nums shrink-0" style={{ color }}>
        {score}
      </span>
    </div>
  );
}

// ─── Deal Card ────────────────────────────────────────────────────────────────

function DealCard({ deal, onStageChange }: { deal: Deal; onStageChange?: (id: string, stage: Stage) => void }) {
  const [stageOpen, setStageOpen] = useState(false);

  const stages: Stage[] = ['tracking', 'in_progress', 'nda_signed', 'closed', 'passed'];

  return (
    <div className="bg-[#111] border border-[#1a1a1a] rounded-xl p-4 flex flex-col gap-3 hover:border-[#2a2a2a] transition-colors">

      {/* Top row: badges */}
      <div className="flex items-center gap-2 flex-wrap">
        <SourceBadge badge={deal.source_badge} />
        <StageBadge stage={deal.stage} />
        {onStageChange && (
          <div className="relative ml-auto">
            <button
              onClick={() => setStageOpen(v => !v)}
              className="font-mono text-[9px] text-gray-700 hover:text-gray-500 transition-colors cursor-pointer uppercase tracking-wider"
            >
              change stage ▾
            </button>
            {stageOpen && (
              <div className="absolute right-0 top-5 z-50 bg-[#111] border border-[#1a1a1a] rounded-lg shadow-2xl overflow-hidden">
                {stages.map(s => (
                  <button
                    key={s}
                    onClick={() => { onStageChange(deal.id, s); setStageOpen(false); }}
                    className="w-full text-left px-3 py-1.5 font-mono text-[10px] text-gray-400 hover:bg-[#1a1a1a] hover:text-white transition-colors cursor-pointer capitalize"
                  >
                    {STAGE_CONFIG[s].label}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Deal name */}
      <div className="font-sans text-sm font-bold text-white leading-snug">
        {deal.name}
      </div>

      {/* Key metrics */}
      <div className="grid grid-cols-4 gap-2">
        <div className="flex flex-col gap-0.5">
          <span className="font-mono text-[9px] text-gray-600 uppercase tracking-widest">Net/mo</span>
          <span className="font-mono text-xs text-gray-200 font-semibold tabular-nums">{fmtK(deal.net_mo)}</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="font-mono text-[9px] text-gray-600 uppercase tracking-widest">Asking</span>
          <span className="font-mono text-xs text-gray-200 font-semibold tabular-nums">{fmtK(deal.asking)}</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="font-mono text-[9px] text-gray-600 uppercase tracking-widest">Multiple</span>
          <span className="font-mono text-xs text-gray-200 font-semibold tabular-nums">{deal.multiple.toFixed(1)}x</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="font-mono text-[9px] text-gray-600 uppercase tracking-widest">Age</span>
          <span className="font-mono text-xs text-gray-200 font-semibold tabular-nums">{deal.age_yr}yr</span>
        </div>
      </div>

      {/* AI-Proof bar */}
      <div className="flex flex-col gap-1">
        <div className="flex items-center justify-between">
          <span className="font-mono text-[9px] text-gray-600 uppercase tracking-widest">AI-Proof Score</span>
        </div>
        <AIProofBar score={deal.ai_proof} />
      </div>

      {/* EVA Score + Net after HELOC */}
      <div className="flex items-end justify-between">
        <div className="flex flex-col gap-0.5">
          <span className="font-mono text-[9px] text-gray-600 uppercase tracking-widest">Net after HELOC</span>
          <span className="font-mono text-sm font-bold text-[#00ff88]">
            +{fmt$(deal.net_after_heloc)}/mo
          </span>
        </div>
        <div className="flex flex-col items-end gap-0.5">
          <span className="font-mono text-[9px] text-gray-600 uppercase tracking-widest">EVA Score</span>
          <span className="font-mono text-2xl font-bold text-white tabular-nums leading-none">
            {deal.eva_score.toFixed(2)}
          </span>
        </div>
      </div>

      {/* Bottom row: decision + link */}
      <div className="flex items-center justify-between pt-1 border-t border-[#1a1a1a]">
        <DecisionBadge decision={deal.decision} />
        <a
          href={deal.url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 font-mono text-[11px] text-gray-500 hover:text-[#00ff88] transition-colors"
        >
          View Listing
          <ExternalLink className="w-3 h-3" />
        </a>
      </div>
    </div>
  );
}

// ─── Skeleton Placeholder Card ────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div className="bg-[#111] border border-[#1a1a1a] rounded-xl p-4 flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <div className="h-4 w-10 bg-[#1a1a1a] rounded animate-pulse" />
        <div className="h-4 w-16 bg-[#1a1a1a] rounded animate-pulse" />
      </div>
      <div className="h-4 w-3/4 bg-[#1a1a1a] rounded animate-pulse" />
      <div className="grid grid-cols-4 gap-2">
        {[0,1,2,3].map(i => (
          <div key={i} className="flex flex-col gap-1">
            <div className="h-2 w-full bg-[#1a1a1a] rounded animate-pulse" />
            <div className="h-3 w-3/4 bg-[#1a1a1a] rounded animate-pulse" />
          </div>
        ))}
      </div>
      <div className="h-2 w-full bg-[#1a1a1a] rounded animate-pulse" />
      <div className="flex items-end justify-between">
        <div className="h-5 w-24 bg-[#1a1a1a] rounded animate-pulse" />
        <div className="h-8 w-12 bg-[#1a1a1a] rounded animate-pulse" />
      </div>
      <div className="flex items-center justify-between pt-1 border-t border-[#1a1a1a]">
        <div className="h-4 w-10 bg-[#1a1a1a] rounded animate-pulse" />
        <div className="h-3 w-20 bg-[#1a1a1a] rounded animate-pulse" />
      </div>
    </div>
  );
}

// ─── Scout Running State ──────────────────────────────────────────────────────

function ScoutRunningPanel({
  label,
  sources,
  buttonLabel,
  endpoint,
}: {
  label: string;
  sources: string[];
  buttonLabel: string;
  endpoint: string;
}) {
  const [loading, setLoading] = useState(false);
  const [triggered, setTriggered] = useState(false);
  const [error, setError] = useState('');

  const runScout = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      await fetch(endpoint, { method: 'POST', signal: AbortSignal.timeout(8000) });
      setTriggered(true);
    } catch {
      setError('Scout API offline — run will start when service comes online.');
    } finally {
      setLoading(false);
    }
  }, [endpoint]);

  return (
    <div className="flex flex-col gap-4">
      {/* Scanning label */}
      <div className="bg-[#111] border border-[#1a1a1a] rounded-xl p-4 flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-[#00ff88] animate-pulse" />
          <span className="font-mono text-xs text-[#00ff88] font-semibold">{triggered ? 'Scout triggered — awaiting results…' : 'Scout Ready'}</span>
        </div>
        <p className="font-mono text-xs text-gray-500 leading-relaxed">{label}</p>

        {/* Sources chips */}
        <div className="flex flex-wrap gap-1.5">
          {sources.map(s => (
            <span
              key={s}
              className="px-2 py-0.5 bg-[#0a0a0a] border border-[#1a1a1a] rounded font-mono text-[10px] text-gray-600"
            >
              {s}
            </span>
          ))}
        </div>

        {error && (
          <div className="px-3 py-2 bg-yellow-500/10 border border-yellow-500/20 rounded font-mono text-[10px] text-yellow-400">
            ⚠ {error}
          </div>
        )}

        <button
          onClick={runScout}
          disabled={loading || triggered}
          className="flex items-center justify-center gap-2 py-2 bg-[#00ff88]/10 border border-[#00ff88]/30 text-[#00ff88] rounded-lg font-mono text-xs font-bold hover:bg-[#00ff88]/20 hover:border-[#00ff88]/60 active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed transition-all cursor-pointer"
        >
          {loading ? (
            <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Running Scout…</>
          ) : triggered ? (
            <><Zap className="w-3.5 h-3.5" /> Scout Running</>
          ) : (
            <><Zap className="w-3.5 h-3.5" /> {buttonLabel}</>
          )}
        </button>
      </div>

      {/* Skeleton cards */}
      <SkeletonCard />
      <SkeletonCard />
      <SkeletonCard />
    </div>
  );
}

// ─── Stats Bar ────────────────────────────────────────────────────────────────

function StatsBar({ deals }: { deals: Deal[] }) {
  const total = deals.length;
  const avgAI = total > 0
    ? Math.round(deals.reduce((a, d) => a + d.ai_proof, 0) / total * 100) / 100
    : 0;
  const bestHeloc = total > 0
    ? Math.max(...deals.map(d => d.net_after_heloc))
    : 0;

  const stats = [
    { icon: BarChart2, label: 'Total Tracked', value: String(total) },
    { icon: Zap,       label: 'Avg AI-Proof',  value: avgAI.toFixed(2) },
    { icon: TrendingUp,label: 'Best Net/HELOC', value: `+${fmt$(bestHeloc)}/mo` },
    { icon: DollarSign,label: 'HELOC Remaining',value: '~$115K' },
  ];

  return (
    <div className="grid grid-cols-4 gap-3">
      {stats.map(({ icon: Icon, label, value }) => (
        <div
          key={label}
          className="bg-[#111] border border-[#1a1a1a] rounded-lg px-3 py-2.5 flex items-center gap-2.5"
        >
          <div className="p-1.5 bg-[#00ff88]/10 rounded-md shrink-0">
            <Icon className="w-3.5 h-3.5 text-[#00ff88]" />
          </div>
          <div className="flex flex-col gap-0.5 min-w-0">
            <span className="font-mono text-[9px] text-gray-600 uppercase tracking-widest truncate">{label}</span>
            <span className="font-mono text-xs text-white font-bold tabular-nums truncate">{value}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Sort Controls ────────────────────────────────────────────────────────────

const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: 'score',    label: 'Score'    },
  { key: 'net_mo',   label: 'Net/mo'   },
  { key: 'multiple', label: 'Multiple' },
  { key: 'ai_proof', label: 'AI-Proof' },
];

function sortDeals(deals: Deal[], key: SortKey): Deal[] {
  return [...deals].sort((a, b) => {
    switch (key) {
      case 'score':    return b.eva_score - a.eva_score;
      case 'net_mo':   return b.net_mo - a.net_mo;
      case 'multiple': return a.multiple - b.multiple;
      case 'ai_proof': return b.ai_proof - a.ai_proof;
      default:         return 0;
    }
  });
}

// ─── Category Tab Config ──────────────────────────────────────────────────────

const TABS: { key: CategoryTab; label: string }[] = [
  { key: 'online',         label: 'Online Business' },
  { key: 'healthcare',     label: 'Healthcare CRE'  },
  { key: 'high_potential', label: 'High Potential'  },
];

// ─── Main Component ───────────────────────────────────────────────────────────

export function DealScoutView() {
  const [activeTab, setActiveTab]   = useState<CategoryTab>('online');
  const [sortKey, setSortKey]       = useState<SortKey>('score');
  const [deals, setDeals]           = useState<Deal[]>(SEED_DEALS);
  const [usingCache, setUsingCache] = useState(false);
  const [loading, setLoading]       = useState(false);

  // ── Fetch deals on mount ──────────────────────────────────────────────────

  const fetchDeals = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch('http://localhost:8766/deals', { signal: AbortSignal.timeout(5000) });
      if (r.ok) {
        const data = await r.json();
        const fetched: Deal[] = Array.isArray(data) ? data : data.deals ?? [];
        if (fetched.length > 0) {
          setDeals(fetched);
          setUsingCache(false);
        } else {
          setUsingCache(true);
        }
      } else {
        setUsingCache(true);
      }
    } catch {
      setUsingCache(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDeals();
  }, [fetchDeals]);

  // ── Stage update ──────────────────────────────────────────────────────────

  const handleStageChange = useCallback(async (id: string, stage: Stage) => {
    // Optimistic update
    setDeals(prev => prev.map(d => d.id === id ? { ...d, stage } : d));

    try {
      await fetch(`http://localhost:8766/deals/${id}/stage`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stage }),
        signal: AbortSignal.timeout(5000),
      });
    } catch {
      // Silent — optimistic update stays
    }
  }, []);

  // ── Filtered & sorted deals for current tab ───────────────────────────────

  const tabDeals = deals.filter(d => d.category === activeTab);
  const sortedDeals = sortDeals(tabDeals, sortKey);

  const onlineCount = deals.filter(d => d.category === 'online').length;
  const allCount    = deals.length;

  return (
    <div className="flex flex-col gap-4 h-full min-h-0">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4 shrink-0">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <h2 className="font-sans text-[20px] font-bold text-white leading-none">Deal Scout</h2>
            {usingCache && (
              <span className="px-1.5 py-0.5 bg-yellow-500/15 border border-yellow-500/30 text-yellow-400 font-mono text-[9px] font-bold rounded tracking-wider uppercase">
                Cached Data
              </span>
            )}
          </div>
          <p className="font-mono text-xs text-gray-500">
            3 categories · {allCount} active deal{allCount !== 1 ? 's' : ''} · $200K HELOC deployed
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {/* Sprint pill */}
          <span className="flex items-center gap-1.5 px-3 py-1.5 bg-[#00ff88]/10 border border-[#00ff88]/30 rounded-full">
            <div className="w-1.5 h-1.5 rounded-full bg-[#00ff88] animate-pulse" />
            <span className="font-mono text-[11px] text-[#00ff88] font-bold">Sprint Active · Health/Wellness SaaS</span>
          </span>

          {/* Refresh */}
          <button
            onClick={fetchDeals}
            disabled={loading}
            className="p-1.5 bg-[#111] border border-[#1a1a1a] rounded-lg text-gray-500 hover:text-gray-300 hover:border-[#2a2a2a] disabled:opacity-50 transition-all cursor-pointer"
            title="Refresh deals"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* ── Stats Bar ──────────────────────────────────────────────────────── */}
      <StatsBar deals={deals.filter(d => d.category === 'online')} />

      {/* ── Category Tabs ──────────────────────────────────────────────────── */}
      <div className="flex items-center gap-0 border-b border-[#1a1a1a] shrink-0">
        {TABS.map(tab => {
          const count = deals.filter(d => d.category === tab.key).length;
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`relative px-4 py-2.5 font-mono text-xs font-semibold transition-colors cursor-pointer ${
                isActive ? 'text-white' : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              {tab.label}
              {count > 0 && (
                <span className={`ml-1.5 px-1.5 py-0.5 rounded-full font-mono text-[9px] font-bold ${
                  isActive
                    ? 'bg-[#00ff88]/20 text-[#00ff88]'
                    : 'bg-[#1a1a1a] text-gray-600'
                }`}>
                  {count}
                </span>
              )}
              {isActive && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-[#00ff88] rounded-t" />
              )}
            </button>
          );
        })}
      </div>

      {/* ── Tab Content ────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {activeTab === 'online' && (
          <div className="flex flex-col gap-4 pb-4">
            {/* Sort controls */}
            {onlineCount > 0 && (
              <div className="flex items-center gap-2 shrink-0">
                <span className="font-mono text-[10px] text-gray-600 uppercase tracking-widest">Sort by</span>
                <div className="flex items-center gap-1">
                  {SORT_OPTIONS.map(opt => (
                    <button
                      key={opt.key}
                      onClick={() => setSortKey(opt.key)}
                      className={`px-2.5 py-1 rounded font-mono text-[10px] font-semibold transition-all cursor-pointer ${
                        sortKey === opt.key
                          ? 'bg-[#00ff88]/15 border border-[#00ff88]/40 text-[#00ff88]'
                          : 'bg-[#111] border border-[#1a1a1a] text-gray-500 hover:text-gray-300 hover:border-[#2a2a2a]'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Deal cards */}
            {sortedDeals.length === 0 ? (
              <div className="flex items-center justify-center py-16 bg-[#111] border border-[#1a1a1a] rounded-xl">
                <span className="font-mono text-xs text-gray-600">No deals in this category yet.</span>
              </div>
            ) : (
              sortedDeals.map(deal => (
                <DealCard
                  key={deal.id}
                  deal={deal}
                  onStageChange={handleStageChange}
                />
              ))
            )}
          </div>
        )}

        {activeTab === 'healthcare' && (
          <div className="pb-4">
            <ScoutRunningPanel
              label="Scanning BizBuySell, BizBen, LoopNet for RCFE + Assisted Living..."
              sources={['BizBuySell', 'BizBen', 'LoopNet', 'CoStar']}
              buttonLabel="Run Healthcare Scout"
              endpoint="http://localhost:8766/scout/healthcare"
            />
          </div>
        )}

        {activeTab === 'high_potential' && (
          <div className="pb-4">
            <ScoutRunningPanel
              label="Scanning for Health/Wellness SaaS, Longevity, AI-proof businesses..."
              sources={['Empire Flippers', 'Flippa', 'Acquire.com']}
              buttonLabel="Run High Potential Scout"
              endpoint="http://localhost:8766/scout/high-potential"
            />
          </div>
        )}
      </div>
    </div>
  );
}
