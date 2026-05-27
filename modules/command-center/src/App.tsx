import { useState, useEffect, useCallback } from 'react';
import { PinGate } from './components/PinGate';
import { EVAHome } from './components/EVAHome';
import { ProjectsView } from './components/ProjectsView';
import { AdminView } from './components/AdminView';
import { useDeals } from './hooks/useDeals';
import { useEvaContext } from './hooks/useEvaContext';

const STORAGE_KEY = 'eva_pin_verified';
const SESSION_DURATION_MS = 8 * 60 * 60 * 1000;

function checkPinSession(): boolean {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const { timestamp } = JSON.parse(stored);
      if (Date.now() - timestamp < SESSION_DURATION_MS) return true;
      localStorage.removeItem(STORAGE_KEY);
    }
  } catch {}
  return false;
}

type Tab = 'eva' | 'projects' | 'admin';

/* ─────────────────────────────────────────
   CLOCK
───────────────────────────────────────── */
function Clock() {
  const [time, setTime] = useState(() => {
    const now = new Date();
    return now.toLocaleTimeString('en-US', { hour12: false });
  });

  useEffect(() => {
    const id = setInterval(() => {
      setTime(new Date().toLocaleTimeString('en-US', { hour12: false }));
    }, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <span style={{ fontFamily: 'ui-monospace, SFMono-Regular, monospace', fontSize: 12, color: '#4b5563' }}>
      {time}
    </span>
  );
}

/* ─────────────────────────────────────────
   STATUS DOT
───────────────────────────────────────── */
function StatusDot() {
  const [online, setOnline] = useState(false);

  useEffect(() => {
    const check = async () => {
      try {
        const r = await fetch('http://localhost:8768/health', { signal: AbortSignal.timeout(2000) });
        setOnline(r.ok);
      } catch {
        setOnline(false);
      }
    };
    check();
    const id = setInterval(check, 8000);
    return () => clearInterval(id);
  }, []);

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: online ? '#22c55e' : '#ef4444',
          boxShadow: online ? '0 0 6px rgba(34,197,94,0.6)' : '0 0 6px rgba(239,68,68,0.4)',
          flexShrink: 0,
        }}
      />
      <span style={{ fontSize: 12, color: '#4b5563' }}>
        {online ? 'Online' : 'Offline'}
      </span>
    </div>
  );
}

/* ─────────────────────────────────────────
   TOP BAR
───────────────────────────────────────── */
function TopBar({ active, onSelect }: { active: Tab; onSelect: (t: Tab) => void }) {
  const tabs: { id: Tab; label: string }[] = [
    { id: 'eva', label: 'EVA' },
    { id: 'projects', label: 'Projects' },
    { id: 'admin', label: 'Admin' },
  ];

  return (
    <header
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        height: 48,
        background: '#0a0a0a',
        borderBottom: '1px solid #1e1e1e',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 20px',
        zIndex: 100,
      }}
    >
      {/* Wordmark */}
      <div style={{ fontSize: 18, fontWeight: 700, color: '#06b6d4', letterSpacing: '-0.02em', userSelect: 'none' }}>
        EVA
      </div>

      {/* Center — empty */}
      <div />

      {/* Right: tabs + status + clock */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        {/* Tab pills */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          {tabs.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => onSelect(id)}
              style={{
                padding: '6px 16px',
                borderRadius: 9999,
                fontSize: 13,
                fontWeight: 500,
                border: 'none',
                cursor: 'pointer',
                transition: 'all 150ms',
                background: active === id ? '#06b6d4' : 'transparent',
                color: active === id ? '#000000' : '#6b7280',
              }}
              onMouseEnter={e => {
                if (active !== id) (e.currentTarget as HTMLButtonElement).style.color = '#ffffff';
              }}
              onMouseLeave={e => {
                if (active !== id) (e.currentTarget as HTMLButtonElement).style.color = '#6b7280';
              }}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Status dot */}
        <StatusDot />

        {/* Clock */}
        <Clock />
      </div>
    </header>
  );
}

/* ─────────────────────────────────────────
   DASHBOARD
───────────────────────────────────────── */
function Dashboard() {
  const [activeTab, setActiveTab] = useState<Tab>('eva');

  const {
    pipelineDeals, archivedDeals, allDeals,
    loading: dealsLoading, status: dealsStatus,
    lastUpdated: dealsUpdated, refresh: refreshDeals,
    advanceStage, archiveDeal, unarchiveDeal, getDealHistory,
  } = useDeals();

  const {
    context, loading: contextLoading,
    status: contextStatus, lastUpdated: contextUpdated,
    refresh: refreshContext,
  } = useEvaContext();

  const handleRefreshAll = useCallback(() => {
    refreshDeals();
    refreshContext();
  }, [refreshDeals, refreshContext]);

  // suppress unused warning — hooks kept for ProjectsView
  void handleRefreshAll;

  return (
    <div style={{ minHeight: '100vh', background: '#0a0a0a' }}>
      <TopBar active={activeTab} onSelect={setActiveTab} />

      {/* Content — below fixed top bar */}
      <div style={{ paddingTop: 48 }}>
        {activeTab === 'eva' && <EVAHome />}
        {activeTab === 'projects' && (
          <ProjectsView
            pipelineDeals={pipelineDeals}
            archivedDeals={archivedDeals}
            allDeals={allDeals}
            dealsLoading={dealsLoading}
            dealsStatus={dealsStatus}
            dealsUpdated={dealsUpdated}
            refreshDeals={refreshDeals}
            advanceStage={advanceStage}
            archiveDeal={archiveDeal}
            unarchiveDeal={unarchiveDeal}
            getDealHistory={getDealHistory}
            context={context}
            contextLoading={contextLoading}
            contextStatus={contextStatus}
            contextUpdated={contextUpdated}
            refreshContext={refreshContext}
          />
        )}
        {activeTab === 'admin' && <AdminView />}
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────
   ROOT
───────────────────────────────────────── */
export default function App() {
  const [pinPassed, setPinPassed] = useState<boolean>(() => checkPinSession());
  if (!pinPassed) return <PinGate onVerified={() => setPinPassed(true)} />;
  return <Dashboard />;
}
