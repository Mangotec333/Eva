import { useState, useEffect, useCallback, useRef } from 'react';
import { RefreshCw, Zap, Target, Server, X, Copy, Check, Play, Terminal, Loader2, PowerOff, Power } from 'lucide-react';
import type { ApiStatus } from '../types';

interface CommandHeaderProps {
  apiStatus: ApiStatus;
  onRefreshAll: () => void;
}

// ── Launcher API (:8768) ──────────────────────────────────────────────────────
const LAUNCHER_API = 'http://localhost:8768';

type LauncherStatus = 'online' | 'offline' | 'loading';

interface LauncherStatusResponse {
  services: Record<string, string>;
  online: number;
  total: number;
  all_online: boolean;
}

// ── Clocks ────────────────────────────────────────────────────────────────────
function useLiveClock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

// ── Status pill colours ───────────────────────────────────────────────────────
const STATUS_COLORS: Record<string, string> = {
  online:  'text-green-400',
  offline: 'text-red-400',
  loading: 'text-amber-400',
};
const STATUS_DOT: Record<string, string> = {
  online:  'bg-green-400',
  offline: 'bg-red-400',
  loading: 'bg-amber-400',
};

// ── StatusPill ────────────────────────────────────────────────────────────────
function StatusPill({
  label, status, icon: Icon, command, onClick,
}: {
  label: string;
  status: 'online' | 'offline' | 'loading';
  icon: React.ElementType;
  command?: string;
  onClick?: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const isOffline = status === 'offline';

  const handleCopy = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!command) return;
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {}
  }, [command]);

  return (
    <div
      onClick={isOffline ? onClick : undefined}
      className={`flex items-center gap-1.5 px-2.5 py-1 bg-gray-100 border rounded transition-all duration-150 ${
        isOffline && onClick
          ? 'border-red-500/60 cursor-pointer hover:bg-red-900/20 hover:border-red-400 group'
          : 'border-gray-200 cursor-default'
      }`}
      title={isOffline && command ? `Click to launch · ${command}` : undefined}
    >
      <div className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT[status]} ${status === 'online' ? 'animate-pulse-slow' : ''}`} />
      <Icon className={`w-3 h-3 ${STATUS_COLORS[status]}`} />
      <span className={`font-mono text-xs font-semibold ${STATUS_COLORS[status]}`}>{label}</span>
      <span className="font-mono text-xs text-gray-500 uppercase">{status}</span>
      {isOffline && command && (
        <button onClick={handleCopy} className="ml-0.5 p-0.5 rounded text-gray-500 hover:text-cyan-400 transition-colors" title="Copy launch command">
          {copied ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3" />}
        </button>
      )}
      {isOffline && onClick && (
        <Terminal className="w-3 h-3 text-gray-500 group-hover:text-red-400 transition-colors" />
      )}
    </div>
  );
}

// ── Service row inside launcher panel ────────────────────────────────────────
const SERVICE_LABELS: Record<string, string> = {
  screenpipe:     'Screenpipe',
  logger:         'EVA Logger',
  context_api:    'Context API',
  deal_scout:     'Deal Scout',
  content_engine: 'Content Engine',
};
const SERVICE_PORTS: Record<string, string> = {
  screenpipe:     ':3030',
  logger:         'no port',
  context_api:    ':8765',
  deal_scout:     ':8766',
  content_engine: ':8767',
};
const SERVICE_CMDS: Record<string, string> = {
  screenpipe:     'screenpipe',
  logger:         'cd ~/Eva/modules/logger && python eva_logger.py',
  context_api:    'cd ~/Eva/modules/logger && python eva_context_api.py',
  deal_scout:     'cd ~/Eva/modules/deal-scout && python main.py',
  content_engine: 'cd ~/Eva/modules/content-engine && python main.py',
};

function ServiceRow({
  name, status, onStart, onStop, starting, stopping,
}: {
  name: string;
  status: string;
  onStart: () => void;
  onStop: () => void;
  starting: boolean;
  stopping: boolean;
}) {
  const isOnline = status === 'online';
  const dot = isOnline ? 'bg-green-400' : starting ? 'bg-amber-400 animate-pulse' : 'bg-red-400';
  const statusLabel = starting ? 'starting…' : stopping ? 'stopping…' : status;
  const statusColor = isOnline ? 'text-green-400' : starting || stopping ? 'text-amber-400' : 'text-red-400';

  return (
    <div className="flex flex-col gap-1.5 py-3 border-b border-gray-200 last:border-0">
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full shrink-0 ${dot}`} />
        <span className="font-mono text-sm font-semibold text-gray-800">{SERVICE_LABELS[name]}</span>
        <span className="font-mono text-xs text-gray-500 ml-1">{SERVICE_PORTS[name]}</span>
        <span className={`font-mono text-xs ml-auto ${statusColor}`}>{statusLabel}</span>
        {/* Start / Stop buttons */}
        {!isOnline && !starting && (
          <button
            onClick={onStart}
            className="flex items-center gap-1 px-2 py-0.5 bg-green-500/10 border border-green-500/40 text-green-400 rounded font-mono text-xs hover:bg-green-500/20 transition-all"
          >
            <Power className="w-3 h-3" /> start
          </button>
        )}
        {isOnline && !stopping && (
          <button
            onClick={onStop}
            className="flex items-center gap-1 px-2 py-0.5 bg-red-500/10 border border-red-500/30 text-red-400 rounded font-mono text-xs hover:bg-red-500/20 transition-all"
          >
            <PowerOff className="w-3 h-3" /> stop
          </button>
        )}
        {(starting || stopping) && <Loader2 className="w-3 h-3 text-amber-400 animate-spin" />}
      </div>
      <code className="font-mono text-xs text-cyan-300 bg-white border border-gray-200 rounded px-3 py-1.5 block">
        {SERVICE_CMDS[name]}
      </code>
    </div>
  );
}

// ── Launcher Panel ────────────────────────────────────────────────────────────
function LauncherPanel({ onClose, focusedService }: { onClose: () => void; focusedService?: string }) {
  const [launcherOnline, setLauncherOnline]   = useState(false);
  const [statuses, setStatuses]               = useState<Record<string, string>>({});
  const [onlineCount, setOnlineCount]         = useState(0);
  const [totalCount, setTotalCount]           = useState(0);
  const [launching, setLaunching]             = useState(false);
  const [launchResult, setLaunchResult]       = useState<string | null>(null);
  const [perServiceState, setPerServiceState] = useState<Record<string, 'starting'|'stopping'|null>>({});
  const overlayRef = useRef<HTMLDivElement>(null);
  const pollRef    = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${LAUNCHER_API}/status`, { signal: AbortSignal.timeout(2000) });
      if (!res.ok) throw new Error();
      const data: LauncherStatusResponse = await res.json();
      setLauncherOnline(true);
      setStatuses(data.services);
      setOnlineCount(data.online);
      setTotalCount(data.total);
    } catch {
      setLauncherOnline(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    pollRef.current = setInterval(fetchStatus, 3000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [fetchStatus]);

  const handleLaunchAll = useCallback(async () => {
    setLaunching(true);
    setLaunchResult(null);
    try {
      const res = await fetch(`${LAUNCHER_API}/start`, { method: 'POST', signal: AbortSignal.timeout(10000) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setLaunchResult(`✓ Launched ${data.launched?.length ?? 0} services`);
      setTimeout(fetchStatus, 2500);
    } catch (e) {
      setLaunchResult(`⚠ ${e instanceof Error ? e.message : 'Failed'}`);
    } finally {
      setLaunching(false);
    }
  }, [fetchStatus]);

  const handleStartOne = useCallback(async (name: string) => {
    setPerServiceState(s => ({ ...s, [name]: 'starting' }));
    try {
      await fetch(`${LAUNCHER_API}/start/${name}`, { method: 'POST', signal: AbortSignal.timeout(10000) });
      setTimeout(fetchStatus, 2500);
    } finally {
      setTimeout(() => setPerServiceState(s => ({ ...s, [name]: null })), 3000);
    }
  }, [fetchStatus]);

  const handleStopOne = useCallback(async (name: string) => {
    setPerServiceState(s => ({ ...s, [name]: 'stopping' }));
    try {
      await fetch(`${LAUNCHER_API}/stop/${name}`, { method: 'POST', signal: AbortSignal.timeout(8000) });
      setTimeout(fetchStatus, 1500);
    } finally {
      setTimeout(() => setPerServiceState(s => ({ ...s, [name]: null })), 3000);
    }
  }, [fetchStatus]);

  const handleOverlayClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === overlayRef.current) onClose();
  }, [onClose]);

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className="fixed inset-0 z-[100] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
    >
      <div className="w-full max-w-lg rounded-2xl flex flex-col max-h-[90vh]" style={{ background: 'var(--bg)', border: '1px solid var(--border)', boxShadow: '0 24px 48px rgba(0,0,0,0.12), 0 8px 16px rgba(0,0,0,0.06)' }}>

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 shrink-0">
          <div className="flex items-center gap-2">
            <Play className="w-4 h-4 text-cyan-400" />
            <span className="font-mono text-sm font-bold text-cyan-400 tracking-wider">EVA SERVICE LAUNCHER</span>
            {/* Launcher daemon status */}
            <div className={`flex items-center gap-1 ml-2 px-2 py-0.5 rounded border text-xs font-mono ${
              launcherOnline
                ? 'border-green-500/40 text-green-400 bg-green-500/10'
                : 'border-red-500/40 text-red-400 bg-red-500/10'
            }`}>
              <div className={`w-1.5 h-1.5 rounded-full ${launcherOnline ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`} />
              {launcherOnline ? `daemon :8768` : 'daemon offline'}
            </div>
          </div>
          <button onClick={onClose} className="p-1 text-gray-500 hover:text-gray-500 transition-colors rounded">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Launcher offline notice */}
        {!launcherOnline && (
          <div className="mx-5 mt-4 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
            <p className="font-mono text-xs text-amber-400 font-semibold mb-1">⚠ Launcher daemon not running</p>
            <p className="font-mono text-xs text-gray-500 mb-2">Run this once in Terminal to install it:</p>
            <code className="block text-xs text-cyan-300 bg-white rounded px-3 py-2 border border-gray-200">
              bash ~/Eva/modules/launcher/install-launcher.sh
            </code>
            <p className="font-mono text-[10px] text-gray-500 mt-2">After install, services will be controllable from this button.</p>
          </div>
        )}

        {/* Services list */}
        {launcherOnline && (
          <>
            {/* Summary bar */}
            <div className="flex items-center justify-between px-5 py-2 border-b border-gray-200/50 shrink-0">
              <span className="font-mono text-xs text-gray-500">
                <span className={onlineCount === totalCount ? 'text-green-400 font-bold' : 'text-amber-400 font-bold'}>
                  {onlineCount}/{totalCount}
                </span> services online
              </span>
              {launchResult && (
                <span className={`font-mono text-xs ${launchResult.startsWith('✓') ? 'text-green-400' : 'text-red-400'}`}>
                  {launchResult}
                </span>
              )}
            </div>

            <div className="px-5 overflow-y-auto">
              {Object.keys(SERVICE_LABELS).map(name => (
                <div
                  key={name}
                  className={`rounded transition-colors ${
                    focusedService === SERVICE_LABELS[name]
                      ? 'bg-cyan-500/10 border border-cyan-500/30 -mx-1 px-1'
                      : ''
                  }`}
                >
                  <ServiceRow
                    name={name}
                    status={statuses[name] ?? 'offline'}
                    onStart={() => handleStartOne(name)}
                    onStop={() => handleStopOne(name)}
                    starting={perServiceState[name] === 'starting'}
                    stopping={perServiceState[name] === 'stopping'}
                  />
                </div>
              ))}
            </div>
          </>
        )}

        {/* Footer */}
        <div className="px-5 py-4 border-t border-gray-200 shrink-0">
          {launcherOnline ? (
            <button
              onClick={handleLaunchAll}
              disabled={launching}
              className="flex items-center justify-center gap-2 w-full px-4 py-2.5 bg-cyan-500/10 border border-cyan-500/40 text-cyan-400 rounded font-mono text-xs font-bold hover:bg-cyan-500/20 hover:border-cyan-500/70 active:scale-[0.98] transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {launching
                ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> LAUNCHING…</>
                : <><Play className="w-3.5 h-3.5" /> LAUNCH ALL SERVICES</>}
            </button>
          ) : (
            <p className="font-mono text-xs text-gray-500 text-center">
              Or run manually:{' '}
              <code className="text-cyan-500 bg-white px-1.5 py-0.5 rounded border border-gray-200">
                bash ~/Eva/eva-start.sh
              </code>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Main Header ───────────────────────────────────────────────────────────────
export function CommandHeader({ apiStatus, onRefreshAll }: CommandHeaderProps) {
  const now = useLiveClock();
  const [spinning, setSpinning]         = useState(false);
  const [showLauncher, setShowLauncher] = useState(false);
  const [launcherFocus, setLauncherFocus] = useState<string | undefined>();

  // Poll launcher health to show daemon status in header
  const [launcherAlive, setLauncherAlive] = useState(false);
  useEffect(() => {
    const check = async () => {
      try {
        const r = await fetch(`${LAUNCHER_API}/health`, { signal: AbortSignal.timeout(1500) });
        setLauncherAlive(r.ok);
      } catch { setLauncherAlive(false); }
    };
    check();
    const t = setInterval(check, 8000);
    return () => clearInterval(t);
  }, []);

  const openLauncher = useCallback((focused?: string) => {
    setLauncherFocus(focused);
    setShowLauncher(true);
  }, []);

  const handleRefresh = useCallback(() => {
    setSpinning(true);
    onRefreshAll();
    setTimeout(() => setSpinning(false), 1200);
  }, [onRefreshAll]);

  const dateStr = now.toLocaleDateString('en-US', { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' });
  const timeStr = now.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });

  return (
    <>
      <header
        className="w-full px-5 flex items-center justify-between gap-4 sticky top-0 z-50"
        style={{
          background: 'rgba(255,255,255,0.85)',
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)',
          borderBottom: '1px solid var(--border-light)',
          height: 52,
        }}
      >
        {/* Left: clock */}
        <div className="flex items-center gap-4">
          <div className="hidden sm:flex flex-col items-start">
            <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.01em' }}>
              {timeStr}
            </span>
            <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{dateStr}</span>
          </div>
        </div>

        {/* Center: mission */}
        <div className="hidden lg:block">
          <p style={{ fontSize: 12, color: 'var(--text-secondary)', textAlign: 'center' }}>
            Target{' '}
            <span style={{ color: 'var(--accent)', fontWeight: 600 }}>$10K/mo</span>
            {' '}· One Man Army
          </p>
        </div>

        {/* Right: status + actions */}
        <div className="flex items-center gap-2 shrink-0">
          {/* Deal Scout status */}
          <div
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full"
            style={{
              background: apiStatus.dealScout === 'online' ? 'var(--accent-light)' : 'var(--bg-secondary)',
              fontSize: 12,
              fontWeight: 500,
              color: apiStatus.dealScout === 'online' ? 'var(--accent-dark)' : 'var(--text-tertiary)',
            }}
          >
            <span className={`agent-dot ${apiStatus.dealScout === 'online' ? 'agent-dot-running' : 'agent-dot-idle'}`} style={{ width: 6, height: 6 }} />
            Deal Scout
          </div>

          {/* Start EVA */}
          <button
            onClick={() => openLauncher()}
            className="eva-btn eva-btn-ghost"
            style={{
              background: launcherAlive ? 'var(--accent-light)' : undefined,
              color: launcherAlive ? 'var(--accent-dark)' : undefined,
              borderColor: launcherAlive ? 'var(--accent)' : undefined,
            }}
            title={launcherAlive ? 'Services online' : 'Start EVA services'}
          >
            {launcherAlive
              ? <><span className="agent-dot agent-dot-running" style={{ width: 6, height: 6 }} /> Online</>
              : <><Play className="w-3 h-3" /> Start EVA</>}
          </button>

          {/* Refresh */}
          <button
            onClick={handleRefresh}
            className="eva-btn eva-btn-ghost"
            title="Refresh all"
            style={{ padding: '7px 10px' }}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${spinning ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </header>

      {showLauncher && <LauncherPanel onClose={() => setShowLauncher(false)} focusedService={launcherFocus} />}
    </>
  );
}
