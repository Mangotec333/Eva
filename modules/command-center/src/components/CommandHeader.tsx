import { useState, useEffect, useCallback, useRef } from 'react';
import { RefreshCw, Zap, Target, Server, X, Copy, Check, Play } from 'lucide-react';
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

// ─── Launch Modal ───────────────────────────────────────────────────────────

type ServiceStatus = 'online' | 'offline' | 'checking';

interface Service {
  name: string;
  endpoint: string | null; // null = manual (no health check)
  command: string;
  manual?: string;
}

const SERVICES: Service[] = [
  {
    name: 'Screenpipe',
    endpoint: 'http://localhost:3030',
    command: 'screenpipe',
  },
  {
    name: 'EVA Logger',
    endpoint: null,
    command: 'cd ~/Eva/modules/logger && python eva_logger.py',
    manual: 'manual — run in terminal',
  },
  {
    name: 'Context API',
    endpoint: 'http://localhost:8765',
    command: 'cd ~/Eva/modules/logger && python eva_context_api.py',
  },
  {
    name: 'Deal Scout',
    endpoint: 'http://localhost:8766',
    command: 'cd ~/Eva/modules/deal-scout && python main.py',
  },
];

const ALL_COMMANDS = SERVICES.map(s => s.command).join('\n');
const LAUNCH_SCRIPT_NOTE = '~/Eva/eva-start.sh';

function ServiceRow({
  service,
  status,
}: {
  service: Service;
  status: ServiceStatus;
}) {
  const dot =
    status === 'online'
      ? 'bg-green-400'
      : status === 'offline'
      ? 'bg-red-400'
      : 'bg-amber-400 animate-pulse';

  const label =
    service.manual
      ? service.manual
      : status === 'online'
      ? 'online'
      : status === 'offline'
      ? 'offline'
      : 'checking…';

  const labelColor =
    status === 'online'
      ? 'text-green-400'
      : status === 'offline'
      ? 'text-red-400'
      : 'text-amber-400';

  return (
    <div className="flex flex-col gap-1.5 py-3 border-b border-gray-800 last:border-0">
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full shrink-0 ${dot}`} />
        <span className="font-mono text-sm font-semibold text-gray-200">{service.name}</span>
        <span className={`font-mono text-xs ml-auto ${labelColor}`}>{label}</span>
      </div>
      <code className="font-mono text-xs text-cyan-300 bg-gray-950 border border-gray-800 rounded px-3 py-1.5 block">
        {service.command}
      </code>
    </div>
  );
}

function LaunchModal({ onClose }: { onClose: () => void }) {
  const [statuses, setStatuses] = useState<ServiceStatus[]>(
    SERVICES.map(s => (s.endpoint ? 'checking' : 'offline'))
  );
  const [copied, setCopied] = useState(false);
  const overlayRef = useRef<HTMLDivElement>(null);

  // Poll health endpoints
  useEffect(() => {
    let cancelled = false;

    async function checkAll() {
      const results = await Promise.all(
        SERVICES.map(async (svc, i) => {
          if (!svc.endpoint) return i; // keep as-is (manual)
          try {
            const res = await fetch(svc.endpoint, { signal: AbortSignal.timeout(2500) });
            return res.ok || res.status < 500 ? 'online' : 'offline';
          } catch {
            return 'offline';
          }
        })
      );
      if (!cancelled) {
        setStatuses(prev =>
          prev.map((s, i) => {
            if (!SERVICES[i].endpoint) return s; // manual: keep offline display
            return (results[i] as ServiceStatus) ?? s;
          })
        );
      }
    }

    checkAll();
    const interval = setInterval(checkAll, 5000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const handleCopyAll = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(ALL_COMMANDS);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback: select textarea
    }
  }, []);

  const handleOverlayClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (e.target === overlayRef.current) onClose();
    },
    [onClose]
  );

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className="fixed inset-0 z-[100] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
    >
      <div className="w-full max-w-lg bg-gray-900 border border-gray-700 rounded-xl shadow-2xl flex flex-col">
        {/* Modal header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <Play className="w-4 h-4 text-cyan-400" />
            <span className="font-mono text-sm font-bold text-cyan-400 tracking-wider">
              START EVA — SERVICE LAUNCHER
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-gray-600 hover:text-gray-300 transition-colors rounded"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Services list */}
        <div className="px-5 py-2">
          {SERVICES.map((svc, i) => (
            <ServiceRow key={svc.name} service={svc} status={statuses[i]} />
          ))}
        </div>

        {/* Footer actions */}
        <div className="px-5 py-4 border-t border-gray-800 flex flex-col gap-3">
          <button
            onClick={handleCopyAll}
            className="flex items-center justify-center gap-2 w-full px-4 py-2.5 bg-cyan-500/10 border border-cyan-500/40 text-cyan-400 rounded font-mono text-xs font-bold hover:bg-cyan-500/20 hover:border-cyan-500/70 active:scale-[0.98] transition-all duration-150"
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5 text-green-400" />
                <span className="text-green-400">COPIED!</span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                COPY ALL COMMANDS
              </>
            )}
          </button>

          <p className="font-mono text-xs text-gray-500 text-center">
            Or run:{' '}
            <code className="text-cyan-500 bg-gray-950 px-1.5 py-0.5 rounded border border-gray-800">
              {LAUNCH_SCRIPT_NOTE}
            </code>{' '}
            to launch all at once
          </p>
        </div>
      </div>
    </div>
  );
}

// ─── Main Header ─────────────────────────────────────────────────────────────

export function CommandHeader({ apiStatus, onRefreshAll }: CommandHeaderProps) {
  const now = useLiveClock();
  const [spinning, setSpinning] = useState(false);
  const [showLauncher, setShowLauncher] = useState(false);

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
    <>
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

        {/* Right: Status Pills + Actions */}
        <div className="flex items-center gap-2 shrink-0">
          <StatusPill label="EVA" status="online" icon={Zap} />
          <StatusPill label="DEAL SCOUT" status={apiStatus.dealScout} icon={Target} />
          <StatusPill label="CONTEXT" status={apiStatus.evaContext} icon={Server} />

          {/* START EVA button */}
          <button
            onClick={() => setShowLauncher(true)}
            className="flex items-center gap-1.5 px-2.5 py-1 bg-cyan-500/20 border border-cyan-400/60 text-cyan-300 rounded font-mono text-xs font-bold hover:bg-cyan-500/30 hover:border-cyan-400 hover:text-cyan-200 active:scale-95 transition-all duration-150"
            title="Launch EVA services"
          >
            <Play className="w-3 h-3" />
            <span>▶ START EVA</span>
          </button>

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

      {showLauncher && <LaunchModal onClose={() => setShowLauncher(false)} />}
    </>
  );
}
