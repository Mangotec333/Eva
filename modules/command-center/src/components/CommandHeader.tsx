import { useState, useEffect, useCallback, useRef } from 'react';
import { RefreshCw, X, Play, Loader2, PowerOff, Power, Copy, Check, Zap } from 'lucide-react';
import type { ApiStatus } from '../types';

interface CommandHeaderProps {
  apiStatus: ApiStatus;
  onRefreshAll: () => void;
  onNavigate?: (tab: string) => void;
}

const LAUNCHER_API = 'http://localhost:8768';

// ── Live clock ────────────────────────────────────────────────────────────────
function useLiveClock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

// ── Service metadata ──────────────────────────────────────────────────────────
const SERVICES: { key: string; label: string; port: string }[] = [
  { key: 'context_api',    label: 'Context API',    port: ':8765' },
  { key: 'deal_scout',     label: 'Deal Scout',     port: ':8766' },
  { key: 'content_engine', label: 'Content Engine', port: ':8767' },
  { key: 'channels',       label: 'Channels Hub',   port: ':8770' },
  { key: 'pathfinder',     label: 'Pathfinder',     port: ':8773' },
  { key: 'voice',          label: 'Voice',          port: ':8774' },
  { key: 'logger',         label: 'Logger',         port: '—'     },
];

// ── Service row ───────────────────────────────────────────────────────────────
function ServiceRow({
  label, port, status, onStart, onStop, busy,
}: {
  label: string; port: string; status: string;
  onStart: () => void; onStop: () => void; busy: boolean;
}) {
  const isOnline  = status === 'online';
  const dotColor  = isOnline ? 'bg-green-400' : busy ? 'bg-amber-400 animate-pulse' : 'bg-red-400/70';

  return (
    <div className="flex items-center gap-3 py-2.5 border-b border-gray-100 last:border-0">
      <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotColor}`} />
      <span className="text-sm font-medium text-gray-800 flex-1">{label}</span>
      <span className="font-mono text-xs text-gray-400">{port}</span>
      {busy ? (
        <Loader2 className="w-3.5 h-3.5 text-amber-400 animate-spin" />
      ) : isOnline ? (
        <button
          onClick={onStop}
          className="p-1 rounded text-gray-400 hover:text-red-400 transition-colors"
          title="Stop"
        >
          <PowerOff className="w-3.5 h-3.5" />
        </button>
      ) : (
        <button
          onClick={onStart}
          className="p-1 rounded text-gray-400 hover:text-green-400 transition-colors"
          title="Start"
        >
          <Power className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}

// ── Boot Modal (launcher offline) ─────────────────────────────────────────────
const BOOT_CMD = 'bash ~/Eva/modules/autostart/eva-boot.sh';

function BootModal({ onClose }: { onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const overlayRef = useRef<HTMLDivElement>(null);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(BOOT_CMD);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {}
  }, []);

  return (
    <div
      ref={overlayRef}
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
      className="fixed inset-0 z-[100] bg-black/50 backdrop-blur-sm flex items-center justify-center p-4"
    >
      <div
        className="w-full max-w-sm rounded-2xl"
        style={{
          background: 'var(--bg)',
          border: '1px solid var(--border)',
          boxShadow: '0 24px 48px rgba(0,0,0,0.10)',
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-5 pb-4">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-amber-400" />
            <span className="text-sm font-semibold text-gray-900">Start EVA</span>
          </div>
          <button onClick={onClose} className="p-1 rounded text-gray-400 hover:text-gray-600 transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-5 pb-5 space-y-4">
          <p className="text-sm text-gray-500">
            Paste this in Terminal to boot all EVA services. The button will turn green automatically once running.
          </p>

          {/* Command block */}
          <div className="relative">
            <code className="block text-sm text-gray-800 font-mono bg-gray-50 border border-gray-200 rounded-xl px-4 py-3 pr-12">
              {BOOT_CMD}
            </code>
            <button
              onClick={handleCopy}
              className="absolute right-3 top-1/2 -translate-y-1/2 p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-all"
              title="Copy"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-green-500" /> : <Copy className="w-3.5 h-3.5" />}
            </button>
          </div>

          <p className="text-xs text-gray-400">
            First time? Run{' '}
            <code className="text-gray-600 bg-gray-100 px-1.5 py-0.5 rounded">
              bash ~/Eva/modules/autostart/eva-install-services.sh
            </code>{' '}
            to register services as Mac login items.
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Launcher Panel (launcher online) ──────────────────────────────────────────
function LauncherPanel({ onClose }: { onClose: () => void }) {
  const [statuses, setStatuses]   = useState<Record<string, string>>({});
  const [onlineCount, setOnline]  = useState(0);
  const [totalCount, setTotal]    = useState(0);
  const [launching, setLaunching] = useState(false);
  const [launched, setLaunched]   = useState(false);
  const [busy, setBusy]           = useState<Record<string, boolean>>({});
  const overlayRef = useRef<HTMLDivElement>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${LAUNCHER_API}/status`, { signal: AbortSignal.timeout(2000) });
      if (!res.ok) throw new Error();
      const data = await res.json();
      // Support both old (string) and new (object with .status) response shapes
      const flat: Record<string, string> = {};
      for (const [k, v] of Object.entries(data.services)) {
        flat[k] = typeof v === 'string' ? v : (v as { status: string }).status;
      }
      setStatuses(flat);
      setOnline(data.online);
      setTotal(data.total);
    } catch {}
  }, []);

  useEffect(() => {
    fetchStatus();
    const t = setInterval(fetchStatus, 3000);
    return () => clearInterval(t);
  }, [fetchStatus]);

  const handleLaunchAll = useCallback(async () => {
    setLaunching(true);
    try {
      await fetch(`${LAUNCHER_API}/start`, { method: 'POST', signal: AbortSignal.timeout(10000) });
      setLaunched(true);
      setTimeout(fetchStatus, 2500);
    } finally {
      setLaunching(false);
    }
  }, [fetchStatus]);

  const handleStart = useCallback(async (key: string) => {
    setBusy(b => ({ ...b, [key]: true }));
    try {
      await fetch(`${LAUNCHER_API}/start/${key}`, { method: 'POST', signal: AbortSignal.timeout(10000) });
      setTimeout(fetchStatus, 2500);
    } finally {
      setTimeout(() => setBusy(b => ({ ...b, [key]: false })), 3500);
    }
  }, [fetchStatus]);

  const handleStop = useCallback(async (key: string) => {
    setBusy(b => ({ ...b, [key]: true }));
    try {
      await fetch(`${LAUNCHER_API}/stop/${key}`, { method: 'POST', signal: AbortSignal.timeout(8000) });
      setTimeout(fetchStatus, 1500);
    } finally {
      setTimeout(() => setBusy(b => ({ ...b, [key]: false })), 3000);
    }
  }, [fetchStatus]);

  const allOnline = onlineCount > 0 && onlineCount === totalCount;

  return (
    <div
      ref={overlayRef}
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
      className="fixed inset-0 z-[100] bg-black/50 backdrop-blur-sm flex items-center justify-center p-4"
    >
      <div
        className="w-full max-w-sm rounded-2xl flex flex-col max-h-[85vh]"
        style={{
          background: 'var(--bg)',
          border: '1px solid var(--border)',
          boxShadow: '0 24px 48px rgba(0,0,0,0.10)',
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-5 pb-3 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            <span className="text-sm font-semibold text-gray-900">EVA Services</span>
            <span className={`text-xs font-mono px-2 py-0.5 rounded-full ${
              allOnline
                ? 'bg-green-50 text-green-600 border border-green-200'
                : 'bg-amber-50 text-amber-600 border border-amber-200'
            }`}>
              {onlineCount}/{totalCount}
            </span>
          </div>
          <button onClick={onClose} className="p-1 rounded text-gray-400 hover:text-gray-600 transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Service list */}
        <div className="px-5 overflow-y-auto flex-1">
          {SERVICES.map(({ key, label, port }) => (
            <ServiceRow
              key={key}
              label={label}
              port={port}
              status={statuses[key] ?? 'offline'}
              onStart={() => handleStart(key)}
              onStop={() => handleStop(key)}
              busy={!!busy[key]}
            />
          ))}
        </div>

        {/* Footer */}
        <div className="px-5 py-4 shrink-0 border-t border-gray-100">
          <button
            onClick={handleLaunchAll}
            disabled={launching || allOnline}
            className="flex items-center justify-center gap-2 w-full px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
            style={{
              background: allOnline ? 'var(--bg-secondary)' : 'var(--accent)',
              color: allOnline ? 'var(--text-tertiary)' : '#fff',
            }}
          >
            {launching
              ? <><Loader2 className="w-4 h-4 animate-spin" /> Starting…</>
              : launched && allOnline
                ? <><span className="w-2 h-2 rounded-full bg-green-300 inline-block" /> All online</>
                : <><Play className="w-4 h-4" /> Start all</>}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main Header ───────────────────────────────────────────────────────────────
export function CommandHeader({ apiStatus, onRefreshAll, onNavigate }: CommandHeaderProps) {
  const now = useLiveClock();
  const [spinning, setSpinning]       = useState(false);
  const [modal, setModal]             = useState<'none' | 'boot' | 'launcher'>('none');
  const [launcherAlive, setLauncher]  = useState(false);

  // Poll launcher every 8s
  useEffect(() => {
    const check = async () => {
      try {
        const r = await fetch(`${LAUNCHER_API}/health`, { signal: AbortSignal.timeout(1500) });
        setLauncher(r.ok);
      } catch { setLauncher(false); }
    };
    check();
    const t = setInterval(check, 8000);
    return () => clearInterval(t);
  }, []);

  const handleEvaClick = useCallback(() => {
    if (launcherAlive) setModal('launcher');
    else setModal('boot');
  }, [launcherAlive]);

  const handleRefresh = useCallback(() => {
    setSpinning(true);
    onRefreshAll();
    setTimeout(() => setSpinning(false), 1200);
  }, [onRefreshAll]);

  const timeStr = now.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const dateStr = now.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });

  return (
    <>
      <header
        className="w-full px-5 flex items-center justify-between gap-4 sticky top-0 z-50"
        style={{
          background: 'rgba(255,255,255,0.90)',
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)',
          borderBottom: '1px solid var(--border-light)',
          height: 52,
        }}
      >
        {/* Left: clock */}
        <div className="hidden sm:flex flex-col items-start">
          <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.01em' }}>
            {timeStr}
          </span>
          <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{dateStr}</span>
        </div>

        {/* Center: mission */}
        <div className="hidden lg:block">
          <p style={{ fontSize: 12, color: 'var(--text-secondary)', textAlign: 'center' }}>
            Target{' '}
            <span style={{ color: 'var(--accent)', fontWeight: 600 }}>$10K/mo</span>
            {' '}· One Man Army
          </p>
        </div>

        {/* Right: actions */}
        <div className="flex items-center gap-2 shrink-0">

          {/* Deal Scout pill — compact, navigates to Acquire */}
          <button
            onClick={() => onNavigate?.('acquire')}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-xs font-medium transition-all duration-150 hover:opacity-75 active:scale-95"
            style={{
              background: apiStatus.dealScout === 'online' ? 'var(--accent-light)' : 'var(--bg-secondary)',
              color: apiStatus.dealScout === 'online' ? 'var(--accent-dark)' : 'var(--text-tertiary)',
            }}
            title="Deal Scout"
          >
            <span className={`w-1.5 h-1.5 rounded-full ${apiStatus.dealScout === 'online' ? 'bg-green-400 animate-pulse' : 'bg-gray-400'}`} />
            Scout
          </button>

          {/* EVA boot/status button */}
          <button
            onClick={handleEvaClick}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-150 hover:opacity-75 active:scale-95"
            style={{
              background: launcherAlive ? 'var(--accent-light)' : 'var(--bg-secondary)',
              color: launcherAlive ? 'var(--accent-dark)' : 'var(--text-secondary)',
            }}
            title={launcherAlive ? 'Manage EVA services' : 'Boot EVA'}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${launcherAlive ? 'bg-green-400 animate-pulse' : 'bg-gray-400'}`} />
            {launcherAlive ? 'Online' : 'Start EVA'}
          </button>

          {/* Refresh */}
          <button
            onClick={handleRefresh}
            className="p-2 rounded-full text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-all active:scale-95"
            title="Refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${spinning ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </header>

      {modal === 'boot'     && <BootModal     onClose={() => setModal('none')} />}
      {modal === 'launcher' && <LauncherPanel onClose={() => setModal('none')} />}
    </>
  );
}
