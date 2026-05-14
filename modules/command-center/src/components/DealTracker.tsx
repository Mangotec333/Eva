import { useState, useCallback } from 'react';
import {
  Target,
  ExternalLink,
  TrendingUp,
  AlertTriangle,
  WifiOff,
  RefreshCw,
  ChevronRight,
  Archive,
  Clock,
  RotateCcw,
  X,
  Check,
} from 'lucide-react';
import type { Deal, DealHistory } from '../types';

// ─── Types ────────────────────────────────────────────────────────────────────

interface DealTrackerProps {
  pipelineDeals: Record<string, Deal[]>;
  archivedDeals: Deal[];
  allDeals: Deal[];
  loading: boolean;
  status: 'online' | 'offline' | 'loading';
  lastUpdated: Date | null;
  onRefresh: () => void;
  onAdvanceStage: (id: string, stage: string, reason: string) => Promise<void>;
  onArchive: (id: string, reason: string) => Promise<void>;
  onUnarchive: (id: string) => Promise<void>;
  onGetHistory: (id: string) => Promise<DealHistory[]>;
}

// ─── Pipeline stage order + config ────────────────────────────────────────────

const STAGE_ORDER = [
  'Tracking',
  'In Progress',
  'NDA Signed',
  'LOI Sent',
  'Due Diligence',
  'Closed',
];

const STAGE_CONFIG: Record<string, { bg: string; text: string; border: string }> = {
  Tracking:       { bg: 'bg-gray-700/30',    text: 'text-gray-400',   border: 'border-gray-700/40' },
  'In Progress':  { bg: 'bg-cyan-500/15',    text: 'text-cyan-400',   border: 'border-cyan-500/30' },
  'NDA Signed':   { bg: 'bg-blue-500/15',    text: 'text-blue-400',   border: 'border-blue-500/30' },
  'LOI Sent':     { bg: 'bg-amber-500/15',   text: 'text-amber-400',  border: 'border-amber-500/30' },
  'Due Diligence':{ bg: 'bg-purple-500/15',  text: 'text-purple-400', border: 'border-purple-500/30' },
  Closed:         { bg: 'bg-green-500/15',   text: 'text-green-400',  border: 'border-green-500/30' },
  Archived:       { bg: 'bg-red-500/10',     text: 'text-red-400',    border: 'border-red-500/20' },
};

const TAB_ORDER = ['All', ...STAGE_ORDER, 'Archived'];

function nextStage(current: string): string | null {
  const idx = STAGE_ORDER.indexOf(current);
  if (idx < 0 || idx >= STAGE_ORDER.length - 1) return null;
  return STAGE_ORDER[idx + 1];
}

// ─── Utility ─────────────────────────────────────────────────────────────────

function formatCurrency(n: number | undefined): string {
  if (n === undefined || n === null) return '—';
  if (Math.abs(n) >= 1000) return `$${(n / 1000).toFixed(1)}K`;
  return `$${n.toLocaleString()}`;
}

function formatDate(s: string | undefined): string {
  if (!s) return '—';
  try {
    return new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });
  } catch {
    return s;
  }
}

// ─── Badges ──────────────────────────────────────────────────────────────────

function StageBadge({ stage }: { stage: string }) {
  const cfg = STAGE_CONFIG[stage] ?? STAGE_CONFIG['Tracking'];
  return (
    <span className={`px-2 py-0.5 rounded border font-mono text-[10px] font-bold uppercase ${cfg.bg} ${cfg.text} ${cfg.border}`}>
      {stage}
    </span>
  );
}

function MarketStatusBadge({ status }: { status: string }) {
  const s = status?.toLowerCase() ?? '';
  const cfg =
    s === 'available'
      ? { bg: 'bg-green-500/15', text: 'text-green-400', border: 'border-green-500/30', label: 'AVAILABLE' }
      : s === 'sold'
      ? { bg: 'bg-red-500/15', text: 'text-red-400', border: 'border-red-500/30', label: 'SOLD' }
      : { bg: 'bg-gray-700/30', text: 'text-gray-400', border: 'border-gray-700/40', label: 'OFF MARKET' };

  return (
    <span className={`px-2 py-0.5 rounded border font-mono text-[10px] font-semibold ${cfg.bg} ${cfg.text} ${cfg.border}`}>
      {cfg.label}
    </span>
  );
}

function AIProofBadge({ score }: { score: number }) {
  const config =
    score >= 80
      ? { bg: 'bg-green-500/15', text: 'text-green-400', border: 'border-green-500/30', label: 'AI-PROOF' }
      : score >= 60
      ? { bg: 'bg-amber-500/15', text: 'text-amber-400', border: 'border-amber-500/30', label: 'MODERATE' }
      : { bg: 'bg-red-500/15', text: 'text-red-400', border: 'border-red-500/30', label: 'AT-RISK' };

  return (
    <div className={`flex items-center gap-1 px-2 py-0.5 rounded border text-xs font-mono font-bold ${config.bg} ${config.text} ${config.border}`}>
      <TrendingUp className="w-3 h-3" />
      {score}
      <span className="text-[10px] font-normal opacity-70">{config.label}</span>
    </div>
  );
}

function BuyBuildBadge({ decision, score }: { decision: string; score: number }) {
  const d = decision?.toLowerCase() ?? '';
  const cfg =
    d === 'buy'
      ? { bg: 'bg-green-500/15', text: 'text-green-400', border: 'border-green-500/30', label: 'BUY' }
      : d === 'build'
      ? { bg: 'bg-blue-500/15', text: 'text-blue-400', border: 'border-blue-500/30', label: 'BUILD' }
      : { bg: 'bg-purple-500/15', text: 'text-purple-400', border: 'border-purple-500/30', label: 'HYBRID' };

  if (!decision) return null;

  return (
    <div className={`flex items-center gap-1 px-2 py-0.5 rounded border font-mono text-[10px] font-bold ${cfg.bg} ${cfg.text} ${cfg.border}`}>
      {cfg.label}
      <span className="font-normal opacity-70">{score}</span>
    </div>
  );
}

function SourceBadge({ source }: { source: string }) {
  const lower = source?.toLowerCase() ?? '';
  const config =
    lower.includes('empire') || lower.includes('ef')
      ? { bg: 'bg-purple-500/10', text: 'text-purple-400', border: 'border-purple-500/20' }
      : lower.includes('flippa')
      ? { bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/20' }
      : lower.includes('acquire')
      ? { bg: 'bg-orange-500/10', text: 'text-orange-400', border: 'border-orange-500/20' }
      : { bg: 'bg-gray-700/20', text: 'text-gray-500', border: 'border-gray-700/30' };

  return (
    <span className={`px-1.5 py-0.5 rounded border font-mono text-[10px] font-semibold uppercase tracking-wide ${config.bg} ${config.text} ${config.border}`}>
      {source ?? 'UNKNOWN'}
    </span>
  );
}

function OverallScoreBar({ score }: { score: number }) {
  const width = Math.min(Math.max(score, 0), 100);
  const color =
    score >= 75 ? 'bg-green-400' :
    score >= 55 ? 'bg-cyan-400' :
    score >= 40 ? 'bg-amber-400' :
    'bg-red-400';

  return (
    <div className="flex items-center gap-2 min-w-[80px]">
      <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
        <div
          className={`h-full ${color} rounded-full transition-all duration-500`}
          style={{ width: `${width}%` }}
        />
      </div>
      <span className="font-mono text-xs text-gray-400 tabular-nums w-6 text-right">{score}</span>
    </div>
  );
}

// ─── Modals ───────────────────────────────────────────────────────────────────

function ModalOverlay({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  return (
    <div
      className="fixed inset-0 z-[200] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      {children}
    </div>
  );
}

function AdvanceStageModal({
  deal,
  onClose,
  onSubmit,
}: {
  deal: Deal;
  onClose: () => void;
  onSubmit: (reason: string) => Promise<void>;
}) {
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const next = nextStage(deal.stage);

  const handleSubmit = async () => {
    if (!reason.trim()) { setError('Reason is required.'); return; }
    if (!next) return;
    setSubmitting(true);
    try {
      await onSubmit(reason.trim());
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to advance stage');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ModalOverlay onClose={onClose}>
      <div className="w-full max-w-md bg-gray-900 border border-gray-700 rounded-xl shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <span className="font-mono text-sm font-bold text-cyan-400 tracking-wider">ADVANCE STAGE</span>
          <button onClick={onClose} className="p-1 text-gray-600 hover:text-gray-300 rounded transition-colors"><X className="w-4 h-4" /></button>
        </div>
        <div className="px-5 py-4 flex flex-col gap-4">
          <div className="flex items-center gap-3 font-mono text-sm">
            <StageBadge stage={deal.stage} />
            <ChevronRight className="w-4 h-4 text-gray-600" />
            {next ? <StageBadge stage={next} /> : <span className="text-gray-600">—</span>}
          </div>
          <div>
            <label className="font-mono text-xs text-gray-500 uppercase tracking-wide block mb-1.5">Reason *</label>
            <textarea
              className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2 font-mono text-sm text-gray-200 resize-none focus:outline-none focus:border-cyan-500/60 transition-colors"
              rows={3}
              placeholder="Why is this deal advancing?"
              value={reason}
              onChange={e => { setReason(e.target.value); setError(''); }}
            />
            {error && <p className="font-mono text-xs text-red-400 mt-1">{error}</p>}
          </div>
        </div>
        <div className="px-5 py-4 border-t border-gray-800 flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-1.5 font-mono text-xs text-gray-500 hover:text-gray-300 border border-gray-700 rounded transition-colors">Cancel</button>
          <button
            onClick={handleSubmit}
            disabled={submitting || !next}
            className="flex items-center gap-1.5 px-4 py-1.5 bg-cyan-500/15 border border-cyan-500/40 text-cyan-400 rounded font-mono text-xs font-bold hover:bg-cyan-500/25 disabled:opacity-50 transition-all"
          >
            {submitting ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
            {submitting ? 'Advancing…' : 'Advance'}
          </button>
        </div>
      </div>
    </ModalOverlay>
  );
}

function ArchiveModal({
  deal,
  onClose,
  onSubmit,
}: {
  deal: Deal;
  onClose: () => void;
  onSubmit: (reason: string) => Promise<void>;
}) {
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async () => {
    if (!reason.trim() || reason.trim().length < 10) {
      setError('Archive reason must be at least 10 characters.');
      return;
    }
    setSubmitting(true);
    try {
      await onSubmit(reason.trim());
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to archive deal');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ModalOverlay onClose={onClose}>
      <div className="w-full max-w-md bg-gray-900 border border-red-900/50 rounded-xl shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <Archive className="w-4 h-4 text-red-400" />
            <span className="font-mono text-sm font-bold text-red-400 tracking-wider">ARCHIVE DEAL</span>
          </div>
          <button onClick={onClose} className="p-1 text-gray-600 hover:text-gray-300 rounded transition-colors"><X className="w-4 h-4" /></button>
        </div>
        <div className="px-5 py-4 flex flex-col gap-4">
          <p className="font-mono text-xs text-gray-400">
            Archiving: <span className="text-gray-200 font-semibold">{deal.name}</span>
          </p>
          <div className="px-3 py-2 bg-amber-500/10 border border-amber-500/20 rounded font-mono text-xs text-amber-400">
            ⚠ This deal will be archived with full history preserved
          </div>
          <div>
            <label className="font-mono text-xs text-gray-500 uppercase tracking-wide block mb-1.5">Archive Reason * (min 10 chars)</label>
            <textarea
              className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2 font-mono text-sm text-gray-200 resize-none focus:outline-none focus:border-red-500/60 transition-colors"
              rows={3}
              placeholder="Why is this deal being archived?"
              value={reason}
              onChange={e => { setReason(e.target.value); setError(''); }}
            />
            {error && <p className="font-mono text-xs text-red-400 mt-1">{error}</p>}
          </div>
        </div>
        <div className="px-5 py-4 border-t border-gray-800 flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-1.5 font-mono text-xs text-gray-500 hover:text-gray-300 border border-gray-700 rounded transition-colors">Cancel</button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="flex items-center gap-1.5 px-4 py-1.5 bg-red-500/15 border border-red-500/40 text-red-400 rounded font-mono text-xs font-bold hover:bg-red-500/25 disabled:opacity-50 transition-all"
          >
            {submitting ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Archive className="w-3 h-3" />}
            {submitting ? 'Archiving…' : 'Archive Deal'}
          </button>
        </div>
      </div>
    </ModalOverlay>
  );
}

function HistoryModal({
  deal,
  history,
  loading,
  onClose,
}: {
  deal: Deal;
  history: DealHistory[];
  loading: boolean;
  onClose: () => void;
}) {
  return (
    <ModalOverlay onClose={onClose}>
      <div className="w-full max-w-lg bg-gray-900 border border-gray-700 rounded-xl shadow-2xl max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800 shrink-0">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-cyan-400" />
            <span className="font-mono text-sm font-bold text-cyan-400 tracking-wider">DEAL HISTORY</span>
            <span className="font-mono text-xs text-gray-600">— {deal.name}</span>
          </div>
          <button onClick={onClose} className="p-1 text-gray-600 hover:text-gray-300 rounded transition-colors"><X className="w-4 h-4" /></button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-3">
          {loading ? (
            <div className="flex flex-col gap-2">
              {[1,2,3].map(i => <div key={i} className="h-10 bg-gray-800/50 rounded animate-pulse" />)}
            </div>
          ) : history.length === 0 ? (
            <p className="font-mono text-sm text-gray-600 text-center py-6">No history recorded yet.</p>
          ) : (
            history.map(item => (
              <div key={item.id} className="flex flex-col gap-0.5 py-2.5 border-b border-gray-800 last:border-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs font-semibold text-gray-300 uppercase tracking-wide">{item.event_type}</span>
                  <span className="font-mono text-[10px] text-gray-600">{formatDate(item.created_at)}</span>
                </div>
                {(item.from_value || item.to_value) && (
                  <div className="flex items-center gap-1.5 font-mono text-xs text-gray-500">
                    <span>{item.from_value}</span>
                    <ChevronRight className="w-3 h-3 text-gray-700" />
                    <span className="text-gray-300">{item.to_value}</span>
                  </div>
                )}
                {item.reason && (
                  <p className="font-sans text-xs text-gray-500 mt-0.5">{item.reason}</p>
                )}
                {item.note && (
                  <p className="font-sans text-xs text-gray-600 italic">{item.note}</p>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </ModalOverlay>
  );
}

// ─── Deal Card ────────────────────────────────────────────────────────────────

function DealCard({
  deal,
  onAdvance,
  onArchive,
  onHistory,
  showUnarchive,
  onUnarchive,
}: {
  deal: Deal;
  onAdvance: () => void;
  onArchive: () => void;
  onHistory: () => void;
  showUnarchive?: boolean;
  onUnarchive?: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const hasNext = !!nextStage(deal.stage);

  return (
    <div className="bg-gray-800/60 border border-gray-700/60 hover:bg-gray-800 hover:border-gray-600/80 rounded transition-colors">
      {/* Main row */}
      <div className="flex items-start gap-3 px-3 py-2.5">
        {/* Name + badges */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className="font-mono text-sm font-semibold text-gray-100 truncate">
              {deal.name}
            </span>
            {deal.url && (
              <a
                href={deal.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex-shrink-0 text-gray-600 hover:text-cyan-400 transition-colors"
              >
                <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>
          <div className="flex items-center gap-1.5 flex-wrap">
            <SourceBadge source={deal.source} />
            <StageBadge stage={deal.stage} />
            <MarketStatusBadge status={deal.market_status ?? 'available'} />
            {deal.buy_vs_build_decision && (
              <BuyBuildBadge decision={deal.buy_vs_build_decision} score={deal.buy_vs_build_score ?? 0} />
            )}
          </div>
        </div>

        {/* Metrics */}
        <div className="hidden sm:flex items-center gap-4 shrink-0">
          {/* Monthly net */}
          <div className="text-right min-w-[65px]">
            <div className="font-sans text-[10px] text-gray-600 uppercase tracking-wide">Mo. Net</div>
            <div className="font-mono text-sm font-bold text-green-400 tabular-nums">
              {formatCurrency(deal.monthly_net)}
            </div>
          </div>

          {/* AI Proof */}
          <div className="hidden md:block">
            <AIProofBadge score={deal.ai_proof_score ?? 0} />
          </div>

          {/* Overall score */}
          <div className="hidden lg:block min-w-[95px]">
            <div className="font-sans text-[10px] text-gray-600 uppercase tracking-wide mb-1">Score</div>
            <OverallScoreBar score={deal.overall_score ?? 0} />
          </div>

          {/* Post-HELOC */}
          <div className="hidden xl:block text-right min-w-[70px]">
            <div className="font-sans text-[10px] text-gray-600 uppercase tracking-wide">Post-HELOC</div>
            <div className={`font-mono text-sm font-bold tabular-nums ${(deal.net_after_heloc ?? 0) >= 0 ? 'text-cyan-400' : 'text-red-400'}`}>
              {formatCurrency(deal.net_after_heloc)}
            </div>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-1 shrink-0">
          {showUnarchive ? (
            <button
              onClick={onUnarchive}
              className="flex items-center gap-1 px-2 py-1 text-[10px] font-mono font-bold text-green-400 bg-green-500/10 border border-green-500/20 rounded hover:bg-green-500/20 transition-colors"
              title="Unarchive deal"
            >
              <RotateCcw className="w-3 h-3" />
              Unarchive
            </button>
          ) : (
            <>
              {hasNext && (
                <button
                  onClick={onAdvance}
                  className="flex items-center gap-1 px-2 py-1 text-[10px] font-mono font-bold text-cyan-400 bg-cyan-500/10 border border-cyan-500/20 rounded hover:bg-cyan-500/20 transition-colors"
                  title="Advance to next stage"
                >
                  <ChevronRight className="w-3 h-3" />
                  Advance
                </button>
              )}
              <button
                onClick={onArchive}
                className="p-1.5 text-gray-600 hover:text-red-400 transition-colors rounded"
                title="Archive deal"
              >
                <Archive className="w-3.5 h-3.5" />
              </button>
            </>
          )}
          <button
            onClick={onHistory}
            className="p-1.5 text-gray-600 hover:text-cyan-400 transition-colors rounded"
            title="View history"
          >
            <Clock className="w-3.5 h-3.5" />
          </button>
          {deal.buy_vs_build_reason && (
            <button
              onClick={() => setExpanded(v => !v)}
              className="p-1.5 text-gray-600 hover:text-amber-400 transition-colors rounded text-[10px] font-mono"
              title="Toggle B/B reason"
            >
              {expanded ? '▲' : '▼'}
            </button>
          )}
        </div>
      </div>

      {/* Archive reason row for archived deals */}
      {deal.is_archived && deal.archive_reason && (
        <div className="px-3 pb-2.5 font-sans text-xs text-red-400/80 bg-red-500/5 border-t border-red-900/30">
          <span className="font-mono font-semibold text-red-400">Archive reason: </span>
          {deal.archive_reason}
        </div>
      )}

      {/* Expandable Buy vs Build reason */}
      {expanded && deal.buy_vs_build_reason && (
        <div className="px-3 pb-2.5 font-sans text-xs text-gray-400 bg-gray-900/50 border-t border-gray-800">
          <span className="font-mono font-semibold text-amber-400/80">B/B Reason: </span>
          {deal.buy_vs_build_reason}
        </div>
      )}
    </div>
  );
}

// ─── Empty / Loading state ────────────────────────────────────────────────────

function EmptyState({ status, onRefresh }: { status: string; onRefresh: () => void }) {
  if (status === 'offline') {
    return (
      <div className="mx-2 my-3 flex flex-col items-center justify-center py-8 gap-3 bg-red-500/5 border border-red-500/15 rounded-lg">
        <WifiOff className="w-7 h-7 text-red-400/60" />
        <div className="text-center">
          <div className="font-mono text-sm text-red-400 font-semibold">Deal Scout API offline</div>
          <div className="font-sans text-xs text-gray-500 mt-1">
            Start it: <span className="font-mono text-gray-400">cd ~/Eva/modules/deal-scout && python main.py</span>
          </div>
        </div>
        <button
          onClick={onRefresh}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 border border-gray-700 rounded font-mono text-xs text-gray-400 hover:text-gray-200 hover:border-gray-600 transition-colors"
        >
          <RefreshCw className="w-3 h-3" />
          Retry Connection
        </button>
      </div>
    );
  }

  if (status === 'loading') {
    return (
      <div className="flex flex-col gap-2 py-4">
        {[1, 2, 3].map(i => (
          <div key={i} className="h-14 bg-gray-800/40 rounded border border-gray-800/60 animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center py-10 gap-2">
      <AlertTriangle className="w-6 h-6 text-amber-400/50" />
      <div className="font-mono text-sm text-gray-500">No deals in this stage</div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function DealTracker({
  pipelineDeals,
  archivedDeals,
  allDeals,
  loading,
  status,
  lastUpdated,
  onRefresh,
  onAdvanceStage,
  onArchive,
  onUnarchive,
  onGetHistory,
}: DealTrackerProps) {
  const [activeTab, setActiveTab] = useState<string>('All');

  // Modal state
  const [advanceDeal, setAdvanceDeal] = useState<Deal | null>(null);
  const [archiveDeal, setArchiveDealState] = useState<Deal | null>(null);
  const [historyDeal, setHistoryDeal] = useState<Deal | null>(null);
  const [historyData, setHistoryData] = useState<DealHistory[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const handleOpenHistory = useCallback(
    async (deal: Deal) => {
      setHistoryDeal(deal);
      setHistoryLoading(true);
      try {
        const h = await onGetHistory(deal.id);
        setHistoryData(h);
      } catch {
        setHistoryData([]);
      } finally {
        setHistoryLoading(false);
      }
    },
    [onGetHistory]
  );

  // Compute deals for the active tab
  const dealsForTab: Deal[] = (() => {
    if (activeTab === 'All') return allDeals;
    if (activeTab === 'Archived') return archivedDeals;
    return pipelineDeals[activeTab] ?? [];
  })();

  // Tab counts
  const tabCount = (tab: string) => {
    if (tab === 'All') return allDeals.length;
    if (tab === 'Archived') return archivedDeals.length;
    return (pipelineDeals[tab] ?? []).length;
  };

  return (
    <>
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 flex flex-col gap-3">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Target className="w-4 h-4 text-cyan-400" />
            <span className="font-mono text-xs font-bold text-gray-400 tracking-widest uppercase">
              Deal Pipeline
            </span>
          </div>
          <div className="flex items-center gap-3">
            {lastUpdated && (
              <span className="font-mono text-[10px] text-gray-700 hidden sm:block">
                {lastUpdated.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </span>
            )}
            <button
              onClick={onRefresh}
              className="p-1 text-gray-600 hover:text-cyan-400 transition-colors"
              title="Refresh deals"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {/* Tab bar */}
        <div className="flex items-center gap-1 flex-wrap border-b border-gray-800 pb-2">
          {TAB_ORDER.map(tab => {
            const count = tabCount(tab);
            const isActive = activeTab === tab;
            return (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-2.5 py-1 rounded font-mono text-[11px] font-semibold transition-colors ${
                  isActive
                    ? 'bg-cyan-500/15 text-cyan-400 border border-cyan-500/30'
                    : 'text-gray-500 hover:text-gray-300 border border-transparent hover:border-gray-700'
                }`}
              >
                {tab}
                {count > 0 && (
                  <span className={`ml-1 px-1 rounded text-[9px] ${isActive ? 'bg-cyan-500/20 text-cyan-400' : 'bg-gray-800 text-gray-600'}`}>
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Deal list */}
        {status === 'offline' || (status === 'loading' && dealsForTab.length === 0) ? (
          <EmptyState status={status} onRefresh={onRefresh} />
        ) : dealsForTab.length === 0 ? (
          <EmptyState status="empty" onRefresh={onRefresh} />
        ) : (
          <div className="flex flex-col gap-1.5">
            {dealsForTab.map(deal => (
              <DealCard
                key={deal.id ?? deal.name}
                deal={deal}
                onAdvance={() => setAdvanceDeal(deal)}
                onArchive={() => setArchiveDealState(deal)}
                onHistory={() => handleOpenHistory(deal)}
                showUnarchive={activeTab === 'Archived'}
                onUnarchive={() => onUnarchive(deal.id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Modals */}
      {advanceDeal && (
        <AdvanceStageModal
          deal={advanceDeal}
          onClose={() => setAdvanceDeal(null)}
          onSubmit={async (reason) => {
            const next = nextStage(advanceDeal.stage);
            if (!next) return;
            await onAdvanceStage(advanceDeal.id, next, reason);
          }}
        />
      )}

      {archiveDeal && (
        <ArchiveModal
          deal={archiveDeal}
          onClose={() => setArchiveDealState(null)}
          onSubmit={async (reason) => {
            await onArchive(archiveDeal.id, reason);
          }}
        />
      )}

      {historyDeal && (
        <HistoryModal
          deal={historyDeal}
          history={historyData}
          loading={historyLoading}
          onClose={() => { setHistoryDeal(null); setHistoryData([]); }}
        />
      )}
    </>
  );
}
