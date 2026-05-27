import { useState, useEffect, useCallback } from 'react';
import { ChevronDown, ChevronUp, Plus, Archive, Check, X, Edit2, BookOpen } from 'lucide-react';

// ─── Types ─────────────────────────────────────────────────────────────────────

type IncubationStatus = 'testing' | 'building' | 'evaluating' | 'live' | 'go' | 'nogo' | 'archived';
type Category = 'online_business' | 'healthcare_cre' | 'eva_platform';

interface IncubationMetrics {
  target: string;
  current: string;
  keyword_hits?: number;
  dms_sent?: number;
  demos_booked?: number;
  paying_customers?: number;
  eva_score?: number;
  monthly_net_full_heloc?: number;
  monthly_net_interest_only?: number;
  cash_on_cash?: string;
  recommendations_made?: number;
  actions_taken?: number;
  revenue_generated?: number;
}

interface Incubation {
  id: string;
  name: string;
  tagline: string;
  category: Category;
  status: IncubationStatus;
  week: number;
  max_weeks: number;
  started: string;
  hypothesis: string;
  metrics: IncubationMetrics;
  go_signals: string[];
  nogo_signals: string[];
  resources: string[];
  decision: 'go' | 'nogo' | null;
  reason: string | null;
  outcome: string | null;
  learnings?: string[];
}

// ─── Seed Data ─────────────────────────────────────────────────────────────────

const SEED_INCUBATIONS: Incubation[] = [
  {
    id: 'inc_001',
    name: 'DealScout.ai',
    tagline: 'Deal sourcing for solo acquirers — $49/mo',
    category: 'online_business',
    status: 'testing',
    week: 1,
    max_weeks: 6,
    started: '2026-05-19',
    hypothesis: 'Solo acquisition entrepreneurs will pay $49/mo to score deals automatically vs manual research',
    metrics: {
      target: '$49 MRR in 6 weeks',
      current: '$0',
      keyword_hits: 0,
      dms_sent: 0,
      demos_booked: 0,
      paying_customers: 0,
    },
    go_signals: ['3+ SCOUT keyword comments', '1 paying customer', '5+ demo requests'],
    nogo_signals: ['0 keyword hits after $200 ad spend', '0 responses to 20 DMs'],
    resources: ['Deal Scout module :8766', 'LinkedIn ads $50', 'Angel 3 daily'],
    decision: null,
    reason: null,
    outcome: null,
    learnings: [],
  },
  {
    id: 'inc_002',
    name: 'RCFE Compliance AI',
    tagline: 'Local AI compliance layer for RCFE operators',
    category: 'healthcare_cre',
    status: 'testing',
    week: 1,
    max_weeks: 6,
    started: '2026-05-19',
    hypothesis: 'RCFE operators will pay for AI that flags compliance issues before state audits',
    metrics: {
      target: '5 OPERATOR keyword responses in 6 weeks',
      current: '0',
      keyword_hits: 0,
      dms_sent: 0,
      demos_booked: 0,
      paying_customers: 0,
    },
    go_signals: ['3+ OPERATOR keyword comments', '1 operator conversation', 'Pain confirmed in call'],
    nogo_signals: ['0 OPERATOR hits after $200 ad spend', 'No operators respond to cold outreach'],
    resources: ['LinkedIn ads $50', 'Content Engine :8767'],
    decision: null,
    reason: null,
    outcome: null,
    learnings: [],
  },
  {
    id: 'inc_003',
    name: 'EVA OS — Founder Memory',
    tagline: 'Local-first AI OS for founders. Rewind AI is dead.',
    category: 'eva_platform',
    status: 'building',
    week: 2,
    max_weeks: 6,
    started: '2026-05-12',
    hypothesis: 'Founders who lost Rewind AI will pay $29/mo for local-first memory OS',
    metrics: {
      target: '10 waitlist signups in 6 weeks',
      current: '0',
      keyword_hits: 0,
      dms_sent: 0,
      demos_booked: 0,
      paying_customers: 0,
    },
    go_signals: ['10 waitlist signups', 'GitHub stars from show HN post', 'Inbound DMs after curl install'],
    nogo_signals: ['0 waitlist after show HN post', 'No engagement on install one-liner'],
    resources: ['All EVA modules', 'Knowledge OS :8771', 'Screenpipe bridge'],
    decision: null,
    reason: null,
    outcome: null,
    learnings: [],
  },
  {
    id: 'inc_004',
    name: 'Oxnard RCFE Acquisition',
    tagline: '$190K asking · $11,263/mo net · EVA Score 83.9',
    category: 'healthcare_cre',
    status: 'evaluating',
    week: 1,
    max_weeks: 3,
    started: '2026-05-21',
    hypothesis: 'Acquiring Oxnard RCFE at $190K generates $11,263/mo net after full HELOC amortization — exceeds $10K target',
    metrics: {
      target: 'Signed LOI in 3 weeks',
      current: 'Scoring stage',
      eva_score: 83.9,
      monthly_net_full_heloc: 11263,
      monthly_net_interest_only: 11362,
      cash_on_cash: '70.3%',
    },
    go_signals: ['License transferable confirmed', '3yr P&L verifies $12,945/mo', 'Staff tenure >1yr', 'Census >80%'],
    nogo_signals: ['License not transferable', 'P&L shows <$10K/mo', 'High staff turnover', 'Lease risk unmitigable'],
    resources: ['$200K HELOC', 'Deal Scout :8766'],
    decision: null,
    reason: null,
    outcome: null,
    learnings: [],
  },
  {
    id: 'inc_005',
    name: 'Yaksha (Angel 3)',
    tagline: 'Daily monetization agent — finds best money move every morning',
    category: 'eva_platform',
    status: 'live',
    week: 1,
    max_weeks: 6,
    started: '2026-05-21',
    hypothesis: 'A daily AI agent reviewing all EVA activity will surface 1 actionable revenue move per day, accelerating time-to-first-dollar',
    metrics: {
      target: 'First paying customer within 2 weeks of daily recommendations',
      current: 'Day 1 — first output generated',
      recommendations_made: 1,
      actions_taken: 0,
      revenue_generated: 0,
    },
    go_signals: ['1 paying customer from a Yaksha recommendation', 'User takes action on >50% of daily moves'],
    nogo_signals: ['0 revenue after 3 weeks of daily recommendations', 'Recommendations ignored consistently'],
    resources: ['Angel 3 module', 'Knowledge OS', 'Social DB'],
    decision: null,
    reason: null,
    outcome: null,
    learnings: [],
  },
];

const LS_KEY = 'eva_incubations';

// ─── Helpers ───────────────────────────────────────────────────────────────────

function computeWeek(started: string): number {
  const ms = Date.now() - new Date(started).getTime();
  return Math.max(1, Math.floor(ms / (7 * 24 * 60 * 60 * 1000)) + 1);
}

function daysUntilNextReview(started: string): number {
  const ms = Date.now() - new Date(started).getTime();
  const daysPassed = Math.floor(ms / 86400000);
  const daysIntoWeek = daysPassed % 7;
  return daysIntoWeek === 0 ? 0 : 7 - daysIntoWeek;
}

function avgWeeksRemaining(incubations: Incubation[]): string {
  const active = incubations.filter(i => i.status !== 'archived');
  if (!active.length) return '—';
  const avg = active.reduce((sum, i) => {
    const w = computeWeek(i.started);
    return sum + Math.max(0, i.max_weeks - w);
  }, 0) / active.length;
  return avg.toFixed(1);
}

function loadFromStorage(): Incubation[] {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) return JSON.parse(raw) as Incubation[];
  } catch {
    // ignore
  }
  return SEED_INCUBATIONS;
}

function saveToStorage(data: Incubation[]) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(data));
  } catch {
    // ignore
  }
}

// ─── Status Badge ──────────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<IncubationStatus, { label: string; bg: string; text: string; border: string }> = {
  testing:   { label: 'TESTING',   bg: 'bg-amber-500/15',   text: 'text-amber-400',   border: 'border-amber-500/30'   },
  building:  { label: 'BUILDING',  bg: 'bg-blue-500/15',    text: 'text-blue-400',    border: 'border-blue-500/30'    },
  evaluating:{ label: 'EVALUATING',bg: 'bg-purple-500/15',  text: 'text-purple-400',  border: 'border-purple-500/30'  },
  live:      { label: 'LIVE',      bg: 'bg-[#00ff88]/15',   text: 'text-[#00ff88]',   border: 'border-[#00ff88]/30'   },
  go:        { label: 'GO ✓',      bg: 'bg-[#00ff88]/25',   text: 'text-[#00ff88]',   border: 'border-[#00ff88]/50'   },
  nogo:      { label: 'NO-GO',     bg: 'bg-red-500/15',     text: 'text-red-400',     border: 'border-red-500/30'     },
  archived:  { label: 'ARCHIVED',  bg: 'bg-gray-500/10',    text: 'text-gray-500',    border: 'border-gray-200/30'    },
};

function StatusBadge({ status }: { status: IncubationStatus }) {
  const cfg = STATUS_CONFIG[status];
  return (
    <span className={`px-2 py-0.5 rounded border font-mono text-[9px] font-bold tracking-wider uppercase ${cfg.bg} ${cfg.text} ${cfg.border}`}>
      {cfg.label}
    </span>
  );
}

// ─── Category Badge ────────────────────────────────────────────────────────────

const CAT_CONFIG: Record<Category, { label: string; bg: string; text: string; border: string }> = {
  online_business: { label: 'Online Biz',  bg: 'bg-sky-500/15',    text: 'text-sky-400',    border: 'border-sky-500/30'    },
  healthcare_cre:  { label: 'Health CRE',  bg: 'bg-emerald-500/15',text: 'text-emerald-400',border: 'border-emerald-500/30' },
  eva_platform:    { label: 'EVA Platform',bg: 'bg-violet-500/15', text: 'text-violet-400', border: 'border-violet-500/30'  },
};

function CategoryBadge({ category }: { category: Category }) {
  const cfg = CAT_CONFIG[category];
  return (
    <span className={`px-2 py-0.5 rounded border font-mono text-[9px] font-bold tracking-wider ${cfg.bg} ${cfg.text} ${cfg.border}`}>
      {cfg.label}
    </span>
  );
}

// ─── Week Progress Bar ─────────────────────────────────────────────────────────

function WeekBar({ week, maxWeeks }: { week: number; maxWeeks: number }) {
  const pct = Math.min(100, (week / maxWeeks) * 100);
  const color = week >= 5 ? '#f87171' : week >= 4 ? '#fbbf24' : '#00ff88';

  return (
    <div className="flex items-center gap-2 min-w-0">
      <span className="font-mono text-[10px] text-gray-500 shrink-0 tabular-nums">
        Wk {week}/{maxWeeks}
      </span>
      <div className="flex-1 h-1.5 bg-[#0a0a0a] rounded-full overflow-hidden border border-[#1a1a1a]">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

// ─── Metrics Grid ──────────────────────────────────────────────────────────────

function MetricCell({
  label,
  value,
  editing,
  onEdit,
}: {
  label: string;
  value: string | number;
  editing: boolean;
  onEdit: (val: string) => void;
}) {
  return (
    <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded px-2.5 py-2 flex flex-col gap-0.5">
      <span className="font-mono text-[9px] text-gray-500 uppercase tracking-widest truncate">{label}</span>
      {editing ? (
        <input
          type="text"
          defaultValue={String(value)}
          onChange={e => onEdit(e.target.value)}
          className="font-mono text-xs text-white bg-transparent border-b border-[#00ff88]/40 focus:outline-none w-full tabular-nums"
        />
      ) : (
        <span className="font-mono text-xs text-white font-semibold tabular-nums">{value}</span>
      )}
    </div>
  );
}

// ─── Log Learning Input ────────────────────────────────────────────────────────

function LogLearningInput({
  onSave,
  onCancel,
}: {
  onSave: (text: string) => void;
  onCancel: () => void;
}) {
  const [val, setVal] = useState('');

  return (
    <div className="flex gap-2 mt-1">
      <input
        type="text"
        value={val}
        onChange={e => setVal(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter' && val.trim()) onSave(val.trim());
          if (e.key === 'Escape') onCancel();
        }}
        placeholder="Log a learning or insight…"
        autoFocus
        className="flex-1 bg-[#0a0a0a] border border-[#1a1a1a] rounded px-3 py-1.5 font-mono text-xs text-gray-500 placeholder:text-gray-400 focus:outline-none focus:border-[#00ff88]/40 transition-colors"
      />
      <button
        onClick={() => { if (val.trim()) onSave(val.trim()); }}
        disabled={!val.trim()}
        className="px-3 py-1.5 bg-[#00ff88]/15 border border-[#00ff88]/40 text-[#00ff88] rounded font-mono text-xs font-bold hover:bg-[#00ff88]/25 disabled:opacity-40 disabled:cursor-not-allowed active:scale-95 transition-all cursor-pointer"
      >
        Save
      </button>
      <button
        onClick={onCancel}
        className="px-2 py-1.5 bg-[#111] border border-[#1a1a1a] text-gray-500 rounded font-mono text-xs hover:text-gray-500 active:scale-95 transition-all cursor-pointer"
      >
        Cancel
      </button>
    </div>
  );
}

// ─── Archive Reason Input ──────────────────────────────────────────────────────

function ArchiveReasonInput({
  onConfirm,
  onCancel,
}: {
  onConfirm: (reason: string) => void;
  onCancel: () => void;
}) {
  const [val, setVal] = useState('');

  return (
    <div className="mt-2 p-3 bg-red-500/5 border border-red-500/20 rounded-lg flex flex-col gap-2">
      <span className="font-mono text-[10px] text-red-400 uppercase tracking-widest">Reason for archiving</span>
      <input
        type="text"
        value={val}
        onChange={e => setVal(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter' && val.trim()) onConfirm(val.trim());
          if (e.key === 'Escape') onCancel();
        }}
        placeholder="What did we learn? Why no-go?"
        autoFocus
        className="bg-[#0a0a0a] border border-[#1a1a1a] rounded px-3 py-1.5 font-mono text-xs text-gray-500 placeholder:text-gray-400 focus:outline-none focus:border-red-500/40 transition-colors"
      />
      <div className="flex gap-2">
        <button
          onClick={() => { if (val.trim()) onConfirm(val.trim()); }}
          disabled={!val.trim()}
          className="flex-1 py-1.5 bg-red-500/15 border border-red-500/30 text-red-400 rounded font-mono text-xs font-bold hover:bg-red-500/25 disabled:opacity-40 disabled:cursor-not-allowed active:scale-95 transition-all cursor-pointer"
        >
          Confirm Archive
        </button>
        <button
          onClick={onCancel}
          className="px-3 py-1.5 bg-[#111] border border-[#1a1a1a] text-gray-500 rounded font-mono text-xs hover:text-gray-500 active:scale-95 transition-all cursor-pointer"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

// ─── Incubation Card ───────────────────────────────────────────────────────────

function IncubationCard({
  inc,
  onUpdate,
  onGo,
  onArchive,
  onLogLearning,
}: {
  inc: Incubation;
  onUpdate: (id: string, metrics: Partial<IncubationMetrics>) => void;
  onGo: (id: string) => void;
  onArchive: (id: string, reason: string) => void;
  onLogLearning: (id: string, text: string) => void;
}) {
  const [editing, setEditing]           = useState(false);
  const [editBuf, setEditBuf]           = useState<Partial<IncubationMetrics>>({});
  const [showLearning, setShowLearning] = useState(false);
  const [showArchive, setShowArchive]   = useState(false);
  const [goFlash, setGoFlash]           = useState(false);

  const week = computeWeek(inc.started);
  const isArchived = inc.status === 'archived';

  const handleGoClick = () => {
    setGoFlash(true);
    onGo(inc.id);
    setTimeout(() => setGoFlash(false), 800);
  };

  const handleSaveEdit = () => {
    onUpdate(inc.id, editBuf);
    setEditBuf({});
    setEditing(false);
  };

  // Build metric display cells
  const m = inc.metrics;
  const metricCells: { key: keyof IncubationMetrics; label: string }[] = [];
  if (m.paying_customers !== undefined) metricCells.push({ key: 'paying_customers', label: 'Paying' });
  if (m.keyword_hits     !== undefined) metricCells.push({ key: 'keyword_hits',     label: 'KW Hits' });
  if (m.dms_sent         !== undefined) metricCells.push({ key: 'dms_sent',         label: 'DMs Sent' });
  if (m.demos_booked     !== undefined) metricCells.push({ key: 'demos_booked',     label: 'Demos' });
  if (m.eva_score        !== undefined) metricCells.push({ key: 'eva_score',        label: 'EVA Score' });
  if (m.monthly_net_full_heloc !== undefined) metricCells.push({ key: 'monthly_net_full_heloc', label: 'Net/mo HELOC' });
  if (m.cash_on_cash     !== undefined) metricCells.push({ key: 'cash_on_cash',     label: 'Cash-on-Cash' });
  if (m.recommendations_made !== undefined) metricCells.push({ key: 'recommendations_made', label: 'Recs Made' });
  if (m.actions_taken    !== undefined) metricCells.push({ key: 'actions_taken',    label: 'Actions Taken' });
  if (m.revenue_generated !== undefined) metricCells.push({ key: 'revenue_generated', label: 'Revenue' });

  const displayCells = metricCells.slice(0, 4);

  return (
    <div
      className={`relative flex flex-col gap-3 rounded-xl p-4 border transition-all duration-300 ${
        isArchived
          ? 'bg-[#0d0d0d] border-[#1a1a1a] opacity-60'
          : goFlash
          ? 'bg-[#00ff88]/5 border-[#00ff88]/40'
          : 'bg-[#111] border-[#1a1a1a] hover:border-[#2a2a2a]'
      }`}
    >
      {/* GO flash overlay */}
      {goFlash && (
        <div className="absolute inset-0 rounded-xl bg-[#00ff88]/10 animate-pulse pointer-events-none" />
      )}

      {/* ── Top row: badges + week bar ── */}
      <div className="flex items-center gap-2 flex-wrap">
        <StatusBadge status={inc.status} />
        <CategoryBadge category={inc.category} />
        <div className="flex-1 min-w-[100px]">
          <WeekBar week={week} maxWeeks={inc.max_weeks} />
        </div>
      </div>

      {/* ── Name + tagline ── */}
      <div className="flex flex-col gap-0.5">
        <span className="font-sans text-base font-bold text-white leading-snug">{inc.name}</span>
        <span className="font-mono text-[12px] text-gray-500 leading-snug">{inc.tagline}</span>
      </div>

      {/* ── Hypothesis ── */}
      <p className="font-sans text-[11px] text-gray-500 italic leading-relaxed line-clamp-2">
        {inc.hypothesis}
      </p>

      {/* ── Target vs Current ── */}
      <div className="flex items-center justify-between px-3 py-2 bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg">
        <div className="flex flex-col gap-0.5">
          <span className="font-mono text-[9px] text-gray-500 uppercase tracking-widest">Target</span>
          <span className="font-mono text-xs text-gray-500 font-semibold">{m.target}</span>
        </div>
        <div className="w-px h-6 bg-[#1a1a1a]" />
        <div className="flex flex-col gap-0.5 text-right">
          <span className="font-mono text-[9px] text-gray-500 uppercase tracking-widest">Current</span>
          <span className={`font-mono text-xs font-bold ${m.current === '$0' || m.current === '0' ? 'text-gray-500' : 'text-[#00ff88]'}`}>
            {m.current}
          </span>
        </div>
      </div>

      {/* ── Metric cells ── */}
      {displayCells.length > 0 && (
        <div className="grid grid-cols-4 gap-1.5">
          {displayCells.map(cell => (
            <MetricCell
              key={cell.key}
              label={cell.label}
              value={editing && editBuf[cell.key] !== undefined ? editBuf[cell.key] as string | number : (m[cell.key] ?? '—') as string | number}
              editing={editing}
              onEdit={val => setEditBuf(prev => ({ ...prev, [cell.key]: isNaN(Number(val)) ? val : Number(val) }))}
            />
          ))}
        </div>
      )}

      {/* ── Go / No-Go signals ── */}
      <div className="grid grid-cols-2 gap-2">
        {/* GO signals */}
        <div className="flex flex-col gap-1.5 bg-[#00ff88]/5 border border-[#00ff88]/15 rounded-lg px-2.5 py-2">
          <span className="font-mono text-[9px] text-[#00ff88] uppercase tracking-widest">✅ GO if</span>
          <ul className="flex flex-col gap-1">
            {inc.go_signals.map((s, i) => (
              <li key={i} className="flex items-start gap-1.5">
                <span className="text-[#00ff88]/50 text-[10px] leading-tight shrink-0 mt-0.5">•</span>
                <span className="font-sans text-[10px] text-gray-500 leading-tight">{s}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* NO-GO signals */}
        <div className="flex flex-col gap-1.5 bg-red-500/5 border border-red-500/15 rounded-lg px-2.5 py-2">
          <span className="font-mono text-[9px] text-red-400 uppercase tracking-widest">❌ NO-GO if</span>
          <ul className="flex flex-col gap-1">
            {inc.nogo_signals.map((s, i) => (
              <li key={i} className="flex items-start gap-1.5">
                <span className="text-red-400/50 text-[10px] leading-tight shrink-0 mt-0.5">•</span>
                <span className="font-sans text-[10px] text-gray-500 leading-tight">{s}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* ── Resources ── */}
      <div className="flex flex-wrap gap-1.5">
        {inc.resources.map((r, i) => (
          <span
            key={i}
            className="px-2 py-0.5 bg-[#0a0a0a] border border-[#1a1a1a] rounded font-mono text-[9px] text-gray-500"
          >
            {r}
          </span>
        ))}
      </div>

      {/* ── Learnings list ── */}
      {inc.learnings && inc.learnings.length > 0 && (
        <div className="flex flex-col gap-1.5 bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg px-2.5 py-2">
          <span className="font-mono text-[9px] text-gray-500 uppercase tracking-widest">Learnings</span>
          <ul className="flex flex-col gap-1">
            {inc.learnings.map((l, i) => (
              <li key={i} className="flex items-start gap-1.5">
                <span className="text-violet-400/60 text-[10px] shrink-0 mt-0.5">◆</span>
                <span className="font-sans text-[10px] text-gray-500 leading-tight">{l}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Log learning input ── */}
      {showLearning && (
        <LogLearningInput
          onSave={text => { onLogLearning(inc.id, text); setShowLearning(false); }}
          onCancel={() => setShowLearning(false)}
        />
      )}

      {/* ── Archive reason input ── */}
      {showArchive && (
        <ArchiveReasonInput
          onConfirm={reason => { onArchive(inc.id, reason); setShowArchive(false); }}
          onCancel={() => setShowArchive(false)}
        />
      )}

      {/* ── Archived outcome ── */}
      {isArchived && inc.reason && (
        <div className="px-3 py-2 bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg">
          <span className="font-mono text-[9px] text-gray-500 uppercase tracking-widest block mb-0.5">Reason</span>
          <p className="font-sans text-[11px] text-gray-500 italic">{inc.reason}</p>
        </div>
      )}

      {/* ── Bottom row: decision + action buttons ── */}
      <div className="flex items-center justify-between gap-2 pt-1 border-t border-[#1a1a1a]">
        {/* Decision status */}
        <div>
          {inc.decision === null ? (
            <span className="font-mono text-[10px] text-gray-400 uppercase tracking-wider">Pending Decision</span>
          ) : inc.decision === 'go' ? (
            <span className="font-mono text-[10px] text-[#00ff88] font-bold uppercase tracking-wider">GO ✓</span>
          ) : (
            <span className="font-mono text-[10px] text-red-400 font-bold uppercase tracking-wider">NO-GO ✗</span>
          )}
        </div>

        {/* Action buttons */}
        {!isArchived && (
          <div className="flex items-center gap-1.5">
            {/* Log Learning */}
            <button
              onClick={() => { setShowLearning(v => !v); setShowArchive(false); }}
              className="flex items-center gap-1 px-2 py-1 bg-[#0a0a0a] border border-[#1a1a1a] text-gray-500 rounded font-mono text-[9px] hover:text-violet-400 hover:border-violet-500/30 active:scale-95 transition-all cursor-pointer"
            >
              <BookOpen className="w-2.5 h-2.5" />
              Log Learning
            </button>

            {/* Update Metrics / Save */}
            {editing ? (
              <button
                onClick={handleSaveEdit}
                className="flex items-center gap-1 px-2 py-1 bg-[#00ff88]/15 border border-[#00ff88]/40 text-[#00ff88] rounded font-mono text-[9px] font-bold hover:bg-[#00ff88]/25 active:scale-95 transition-all cursor-pointer"
              >
                <Check className="w-2.5 h-2.5" />
                Save
              </button>
            ) : (
              <button
                onClick={() => { setEditing(true); setShowLearning(false); setShowArchive(false); }}
                className="flex items-center gap-1 px-2 py-1 bg-[#0a0a0a] border border-[#1a1a1a] text-gray-500 rounded font-mono text-[9px] hover:text-gray-500 hover:border-[#2a2a2a] active:scale-95 transition-all cursor-pointer"
              >
                <Edit2 className="w-2.5 h-2.5" />
                Update
              </button>
            )}

            {/* GO / Archive decision buttons */}
            {inc.decision === null && (
              <>
                <button
                  onClick={handleGoClick}
                  className="flex items-center gap-1 px-2.5 py-1 bg-[#00ff88]/15 border border-[#00ff88]/40 text-[#00ff88] rounded font-mono text-[9px] font-bold hover:bg-[#00ff88]/25 active:scale-95 transition-all cursor-pointer"
                >
                  <Check className="w-2.5 h-2.5" />
                  GO →
                </button>
                <button
                  onClick={() => { setShowArchive(v => !v); setShowLearning(false); }}
                  className="flex items-center gap-1 px-2.5 py-1 bg-red-500/10 border border-red-500/30 text-red-400 rounded font-mono text-[9px] font-bold hover:bg-red-500/20 active:scale-95 transition-all cursor-pointer"
                >
                  <Archive className="w-2.5 h-2.5" />
                  Archive →
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Summary Bar ───────────────────────────────────────────────────────────────

function SummaryBar({ incubations }: { incubations: Incubation[] }) {
  const active = incubations.filter(i => i.status !== 'archived');
  const totalResources = active.reduce((n, i) => n + i.resources.length, 0);
  const weeksRemaining = avgWeeksRemaining(incubations);
  const revenue = '$0';

  const stats = [
    { label: 'Active Tests',          value: String(active.length)     },
    { label: 'Resources Deployed',    value: String(totalResources)    },
    { label: 'Weeks Remaining (avg)', value: weeksRemaining            },
    { label: 'Revenue from Incubs',   value: revenue                   },
  ];

  return (
    <div className="grid grid-cols-4 gap-3">
      {stats.map(({ label, value }) => (
        <div
          key={label}
          className="bg-[#111] border border-[#1a1a1a] rounded-lg px-3 py-2.5 flex flex-col gap-1"
        >
          <span className="font-mono text-[9px] text-gray-500 uppercase tracking-widest truncate">{label}</span>
          <span className="font-mono text-base font-bold text-white tabular-nums">{value}</span>
        </div>
      ))}
    </div>
  );
}

// ─── Weekly Review Banner ──────────────────────────────────────────────────────

function WeeklyReviewBanner({ incubations }: { incubations: Incubation[] }) {
  // Use the earliest active started date
  const active = incubations.filter(i => i.status !== 'archived');
  if (!active.length) return null;
  const earliest = active.reduce((min, i) => i.started < min ? i.started : min, active[0].started);
  const daysLeft = daysUntilNextReview(earliest);

  return (
    <div className={`flex items-center justify-between px-4 py-2.5 rounded-lg border ${
      daysLeft === 0
        ? 'bg-amber-500/10 border-amber-500/30'
        : 'bg-[#111] border-[#1a1a1a]'
    }`}>
      <div className="flex items-center gap-2">
        <div className={`w-1.5 h-1.5 rounded-full ${daysLeft === 0 ? 'bg-amber-400 animate-pulse' : 'bg-gray-600'}`} />
        <span className={`font-mono text-[11px] font-semibold ${daysLeft === 0 ? 'text-amber-400' : 'text-gray-500'}`}>
          {daysLeft === 0
            ? '⚡ Weekly review due today — evaluate all incubations'
            : `Weekly review due in ${daysLeft} day${daysLeft !== 1 ? 's' : ''}`}
        </span>
      </div>
      <span className="font-mono text-[10px] text-gray-400 uppercase tracking-widest">
        Every 7 days
      </span>
    </div>
  );
}

// ─── Archive Section ───────────────────────────────────────────────────────────

function ArchiveSection({ archived }: { archived: Incubation[] }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="bg-[#111] border border-[#1a1a1a] rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-[#1a1a1a]/50 transition-colors cursor-pointer"
      >
        <div className="flex items-center gap-2">
          <Archive className="w-3.5 h-3.5 text-gray-500" />
          <span className="font-mono text-[11px] text-gray-500 font-semibold">
            {archived.length} Archived
          </span>
        </div>
        {open ? (
          <ChevronUp className="w-3.5 h-3.5 text-gray-500" />
        ) : (
          <ChevronDown className="w-3.5 h-3.5 text-gray-500" />
        )}
      </button>

      {open && archived.length > 0 && (
        <div className="px-4 pb-4 grid grid-cols-2 gap-3 border-t border-[#1a1a1a]" style={{ paddingTop: '12px' }}>
          {archived.map(inc => (
            <div
              key={inc.id}
              className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg p-3 flex flex-col gap-2 opacity-60"
            >
              <div className="flex items-center gap-2">
                <StatusBadge status="archived" />
                <CategoryBadge category={inc.category} />
              </div>
              <span className="font-sans text-sm font-bold text-gray-500">{inc.name}</span>
              <span className="font-mono text-[10px] text-gray-500">{inc.tagline}</span>
              {inc.reason && (
                <div className="mt-1 px-2.5 py-2 bg-[#111] border border-[#1a1a1a] rounded">
                  <span className="font-mono text-[9px] text-gray-500 uppercase tracking-widest block mb-0.5">Reason</span>
                  <p className="font-sans text-[10px] text-gray-500 italic">{inc.reason}</p>
                </div>
              )}
              {inc.outcome && (
                <div className="px-2.5 py-2 bg-[#111] border border-[#1a1a1a] rounded">
                  <span className="font-mono text-[9px] text-gray-500 uppercase tracking-widest block mb-0.5">Outcome</span>
                  <p className="font-sans text-[10px] text-gray-500">{inc.outcome}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {open && archived.length === 0 && (
        <div className="px-4 py-6 border-t border-[#1a1a1a] text-center">
          <span className="font-mono text-xs text-gray-400">No archived incubations yet.</span>
        </div>
      )}
    </div>
  );
}

// ─── Main Component ────────────────────────────────────────────────────────────

export function IncubationPanel() {
  const [incubations, setIncubations] = useState<Incubation[]>(() => loadFromStorage());

  // Persist on every change
  useEffect(() => {
    saveToStorage(incubations);
  }, [incubations]);

  // ── Handlers ────────────────────────────────────────────────────────────────

  const handleUpdate = useCallback((id: string, metrics: Partial<IncubationMetrics>) => {
    setIncubations(prev =>
      prev.map(i =>
        i.id === id ? { ...i, metrics: { ...i.metrics, ...metrics } } : i
      )
    );
  }, []);

  const handleGo = useCallback((id: string) => {
    setIncubations(prev =>
      prev.map(i =>
        i.id === id ? { ...i, status: 'go', decision: 'go' } : i
      )
    );
  }, []);

  const handleArchive = useCallback((id: string, reason: string) => {
    setIncubations(prev =>
      prev.map(i =>
        i.id === id ? { ...i, status: 'archived', decision: 'nogo', reason } : i
      )
    );
  }, []);

  const handleLogLearning = useCallback((id: string, text: string) => {
    setIncubations(prev =>
      prev.map(i =>
        i.id === id ? { ...i, learnings: [...(i.learnings ?? []), text] } : i
      )
    );
  }, []);

  // ── Derived ─────────────────────────────────────────────────────────────────

  const active   = incubations.filter(i => i.status !== 'archived');
  const archived = incubations.filter(i => i.status === 'archived');

  return (
    <div className="flex flex-col gap-4">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h2 className="font-sans text-[20px] font-bold text-white leading-none">Incubation Lab</h2>
          <p className="font-mono text-xs text-gray-500">
            6-week max · Go or No-Go · Kill fast, fuel winners
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="flex items-center gap-1.5 px-2.5 py-1 bg-[#00ff88]/10 border border-[#00ff88]/30 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-[#00ff88] animate-pulse" />
            <span className="font-mono text-[11px] text-[#00ff88] font-bold">{active.length} active</span>
          </span>
          <span className="flex items-center gap-1.5 px-2.5 py-1 bg-[#1a1a1a] border border-[#2a2a2a] rounded-full">
            <span className="font-mono text-[11px] text-gray-500 font-bold">{archived.length} archived</span>
          </span>
        </div>
      </div>

      {/* ── Weekly Review Banner ────────────────────────────────────────────── */}
      <WeeklyReviewBanner incubations={incubations} />

      {/* ── Summary Bar ─────────────────────────────────────────────────────── */}
      <SummaryBar incubations={incubations} />

      {/* ── Incubation Cards Grid ────────────────────────────────────────────── */}
      {active.length > 0 ? (
        <div className="grid grid-cols-2 gap-4">
          {active.map(inc => (
            <IncubationCard
              key={inc.id}
              inc={inc}
              onUpdate={handleUpdate}
              onGo={handleGo}
              onArchive={handleArchive}
              onLogLearning={handleLogLearning}
            />
          ))}
        </div>
      ) : (
        <div className="flex items-center justify-center py-16 bg-[#111] border border-[#1a1a1a] rounded-xl">
          <div className="flex flex-col items-center gap-2">
            <span className="font-mono text-xs text-gray-500">No active incubations</span>
            <button className="flex items-center gap-1.5 px-3 py-1.5 bg-[#00ff88]/10 border border-[#00ff88]/30 text-[#00ff88] rounded-lg font-mono text-xs font-bold hover:bg-[#00ff88]/20 active:scale-95 transition-all cursor-pointer">
              <Plus className="w-3.5 h-3.5" />
              Add First Incubation
            </button>
          </div>
        </div>
      )}

      {/* ── Archive Section ──────────────────────────────────────────────────── */}
      <ArchiveSection archived={archived} />
    </div>
  );
}
