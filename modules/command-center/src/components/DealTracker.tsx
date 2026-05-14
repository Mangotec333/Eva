import { Target, ExternalLink, TrendingUp, AlertTriangle, WifiOff, RefreshCw } from 'lucide-react';
import type { Deal } from '../types';

interface DealTrackerProps {
  deals: Deal[];
  loading: boolean;
  status: 'online' | 'offline' | 'loading';
  lastUpdated: Date | null;
  onRefresh: () => void;
}

function formatCurrency(n: number | undefined): string {
  if (n === undefined || n === null) return '—';
  if (Math.abs(n) >= 1000) return `$${(n / 1000).toFixed(1)}K`;
  return `$${n.toLocaleString()}`;
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

function StatusPill({ status }: { status: string }) {
  const config =
    status === 'PURSUING'
      ? { bg: 'bg-cyan-500/15', text: 'text-cyan-400', border: 'border-cyan-500/30' }
      : status === 'TRACKING'
      ? { bg: 'bg-amber-500/15', text: 'text-amber-400', border: 'border-amber-500/30' }
      : { bg: 'bg-gray-700/30', text: 'text-gray-500', border: 'border-gray-700/40' };

  return (
    <span className={`px-2 py-0.5 rounded border font-mono text-xs font-semibold ${config.bg} ${config.text} ${config.border}`}>
      {status}
    </span>
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

function DealCard({ deal }: { deal: Deal }) {
  const isPassed = deal.status === 'PASSED';

  return (
    <div
      className={`flex items-center gap-3 px-3 py-2.5 rounded border transition-colors
        ${isPassed
          ? 'bg-gray-900/50 border-gray-800/40 opacity-50'
          : 'bg-gray-800/60 border-gray-700/60 hover:bg-gray-800 hover:border-gray-600/80'}
      `}
    >
      {/* Name + Source */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span className={`font-mono text-sm font-semibold truncate ${isPassed ? 'text-gray-600' : 'text-gray-100'}`}>
            {deal.name}
          </span>
          {deal.url && !isPassed && (
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
        <SourceBadge source={deal.source} />
      </div>

      {/* Monthly Net */}
      <div className="text-right hidden sm:block min-w-[70px]">
        <div className="font-sans text-[10px] text-gray-600 uppercase tracking-wide">Mo. Net</div>
        <div className="font-mono text-sm font-bold text-green-400 tabular-nums">
          {formatCurrency(deal.monthly_net)}
        </div>
      </div>

      {/* AI Proof Score */}
      <div className="hidden md:block">
        <AIProofBadge score={deal.ai_proof_score ?? 0} />
      </div>

      {/* Overall Score */}
      <div className="hidden lg:block min-w-[100px]">
        <div className="font-sans text-[10px] text-gray-600 uppercase tracking-wide mb-1">Score</div>
        <OverallScoreBar score={deal.overall_score ?? 0} />
      </div>

      {/* Net after HELOC */}
      <div className="text-right hidden xl:block min-w-[70px]">
        <div className="font-sans text-[10px] text-gray-600 uppercase tracking-wide">Post-HELOC</div>
        <div className={`font-mono text-sm font-bold tabular-nums ${(deal.net_after_heloc ?? 0) >= 0 ? 'text-cyan-400' : 'text-red-400'}`}>
          {formatCurrency(deal.net_after_heloc)}
        </div>
      </div>

      {/* Status */}
      <StatusPill status={deal.status ?? 'TRACKING'} />
    </div>
  );
}

function EmptyState({ status, onRefresh }: { status: string; onRefresh: () => void }) {
  if (status === 'offline') {
    return (
      <div className="flex flex-col items-center justify-center py-10 gap-3">
        <WifiOff className="w-8 h-8 text-red-400/50" />
        <div className="text-center">
          <div className="font-mono text-sm text-red-400 font-semibold">
            Deal Scout API offline
          </div>
          <div className="font-sans text-xs text-gray-600 mt-1">
            Ensure the Deal Scout service is running on localhost:8766
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
          <div key={i} className="h-12 bg-gray-800/40 rounded border border-gray-800/60 animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center py-10 gap-2">
      <AlertTriangle className="w-6 h-6 text-amber-400/50" />
      <div className="font-mono text-sm text-gray-500">No deals in pipeline</div>
    </div>
  );
}

export function DealTracker({ deals, loading, status, lastUpdated, onRefresh }: DealTrackerProps) {
  const pursuing = deals.filter(d => d.status === 'PURSUING');
  const tracking = deals.filter(d => d.status === 'TRACKING');
  const passed = deals.filter(d => d.status === 'PASSED');

  return (
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
          {/* Counts */}
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs text-cyan-400 font-semibold">{pursuing.length} PURSUING</span>
            <span className="text-gray-700">|</span>
            <span className="font-mono text-xs text-amber-400 font-semibold">{tracking.length} TRACKING</span>
            <span className="text-gray-700">|</span>
            <span className="font-mono text-xs text-gray-600 font-semibold">{passed.length} PASSED</span>
          </div>
          {/* Last updated */}
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

      {/* Column headers — visible on larger screens */}
      {deals.length > 0 && (
        <div className="hidden lg:flex items-center gap-3 px-3 py-1 text-[10px] font-mono text-gray-600 uppercase tracking-wider border-b border-gray-800">
          <div className="flex-1">Deal / Source</div>
          <div className="hidden sm:block w-[70px] text-right">Mo. Net</div>
          <div className="hidden md:block w-[110px]">AI Proof</div>
          <div className="hidden lg:block w-[100px]">Score</div>
          <div className="hidden xl:block w-[70px] text-right">Post-HELOC</div>
          <div className="w-[80px] text-right">Status</div>
        </div>
      )}

      {/* Deal list */}
      {deals.length > 0 ? (
        <div className="flex flex-col gap-1">
          {deals.map(deal => (
            <DealCard key={deal.id ?? deal.name} deal={deal} />
          ))}
        </div>
      ) : (
        <EmptyState status={status} onRefresh={onRefresh} />
      )}
    </div>
  );
}
