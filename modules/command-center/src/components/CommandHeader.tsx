import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Zap, Target, Server } from 'lucide-react';
import type { ApiStatus } from '../types';

interface CommandHeaderProps {
  apiStatus: ApiStatus;
  onRefreshAll: () => void;
}

function useLiveClock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

const STATUS_COLORS: Record<ApiStatus['dealScout'], string> = {
  online: 'text-green-400',
  offline: 'text-red-400',
  loading: 'text-amber-400',
};

const STATUS_DOT: Record<ApiStatus['dealScout'], string> = {
  online: 'bg-green-400',
  offline: 'bg-red-400',
  loading: 'bg-amber-400',
};

function StatusPill({
  label,
  status,
  icon: Icon,
}: {
  label: string;
  status: 'online' | 'offline' | 'loading';
  icon: React.ElementType;
}) {
  return (
    <div className="flex items-center gap-1.5 px-2.5 py-1 bg-gray-800 border border-gray-700 rounded">
      <div
        className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT[status]} ${
          status === 'online' ? 'animate-pulse-slow' : ''
        }`}
      />
      <Icon className={`w-3 h-3 ${STATUS_COLORS[status]}`} />
      <span className={`font-mono text-xs font-semibold ${STATUS_COLORS[status]}`}>
        {label}
      </span>
      <span className="font-mono text-xs text-gray-500 uppercase">{status}</span>
    </div>
  );
}

export function CommandHeader({ apiStatus, onRefreshAll }: CommandHeaderProps) {
  const now = useLiveClock();
  const [spinning, setSpinning] = useState(false);

  const handleRefresh = useCallback(() => {
    setSpinning(true);
    onRefreshAll();
    setTimeout(() => setSpinning(false), 1200);
  }, [onRefreshAll]);

  const dateStr = now.toLocaleDateString('en-US', {
    weekday: 'short',
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });

  const timeStr = now.toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });

  return (
    <header className="w-full bg-gray-900 border-b border-gray-800 px-4 py-2.5 flex items-center justify-between gap-4 sticky top-0 z-50">
      {/* Left: Branding + Clock */}
      <div className="flex items-center gap-4 min-w-0">
        {/* Logo mark */}
        <div className="flex items-center gap-2 shrink-0">
          <svg
            viewBox="0 0 28 28"
            fill="none"
            className="w-7 h-7"
            aria-label="EVA"
          >
            <polygon
              points="14,2 26,22 2,22"
              stroke="#06b6d4"
              strokeWidth="1.8"
              fill="none"
            />
            <circle cx="14" cy="16" r="2.5" fill="#06b6d4" />
            <line x1="14" y1="9" x2="14" y2="13.5" stroke="#06b6d4" strokeWidth="1.5" />
          </svg>
          <div>
            <div className="font-mono text-sm font-bold text-cyan-400 tracking-widest leading-none">
              EVA COMMAND CENTER
            </div>
            <div className="font-mono text-xs text-gray-500 tracking-wide">
              MODULE 4 — PRIORITY DASHBOARD
            </div>
          </div>
        </div>

        {/* Clock */}
        <div className="hidden sm:flex flex-col items-start border-l border-gray-700 pl-4">
          <span className="font-mono text-lg font-bold text-gray-100 tabular-nums leading-none">
            {timeStr}
          </span>
          <span className="font-mono text-xs text-gray-500 leading-none mt-0.5">
            {dateStr}
          </span>
        </div>
      </div>

      {/* Center: Daily Mission */}
      <div className="hidden lg:flex flex-1 justify-center px-4 min-w-0">
        <div className="text-center max-w-xl">
          <div className="font-mono text-xs text-amber-400 font-semibold tracking-widest uppercase mb-0.5">
            ◆ DAILY MISSION
          </div>
          <p className="font-sans text-xs text-gray-300 leading-snug">
            Convert every ounce of energy to revenue.{' '}
            <span className="text-cyan-400 font-semibold">$10K/mo threshold</span> = arrow
            flips.
          </p>
        </div>
      </div>

      {/* Right: Status Pills + Refresh */}
      <div className="flex items-center gap-2 shrink-0">
        <StatusPill label="EVA" status="online" icon={Zap} />
        <StatusPill label="DEAL SCOUT" status={apiStatus.dealScout} icon={Target} />
        <StatusPill label="CONTEXT" status={apiStatus.evaContext} icon={Server} />

        <button
          onClick={handleRefresh}
          className="flex items-center gap-1.5 px-2.5 py-1 bg-cyan-500/10 border border-cyan-500/40 text-cyan-400 rounded font-mono text-xs font-semibold hover:bg-cyan-500/20 hover:border-cyan-500/70 active:scale-95 transition-all duration-150"
          title="Refresh all data sources"
        >
          <RefreshCw className={`w-3 h-3 ${spinning ? 'animate-spin' : ''}`} />
          <span className="hidden sm:inline">REFRESH ALL</span>
        </button>
      </div>
    </header>
  );
}
