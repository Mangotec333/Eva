import { useCallback, useState, useEffect } from 'react';
import { PinGate } from './components/PinGate';
import { CommandHeader } from './components/CommandHeader';
import { RevenueGauge } from './components/RevenueGauge';
import { PriorityStack } from './components/PriorityStack';
import { DealTracker } from './components/DealTracker';
import { EnergyBudget } from './components/EnergyBudget';
import { ActionQueue } from './components/ActionQueue';
import { PriorityRoadmap } from './components/PriorityRoadmap';
import { ActivityFeed } from './components/ActivityFeed';
import { ContentQueue } from './components/ContentQueue';
import { SocialQueue } from './components/SocialQueue';
import RemindersPanel from './components/RemindersPanel';
import { TerminalPanel } from './components/TerminalPanel';
import { ChannelsHub } from './components/ChannelsHub';
import { DealScoutView } from './components/DealScoutView';
import { SocialSignals } from './components/SocialSignals';
import { IncubationPanel } from './components/IncubationPanel';
import { PathfinderLeads } from './components/PathfinderLeads';
import { GlossaiPanel } from './components/GlossaiPanel';
import { MissionRoadmap } from './components/MissionRoadmap';
import { PortfolioMap } from './components/PortfolioMap';
import { WellnessBlocks } from './components/WellnessBlocks';
import { AgentPipeline } from './components/AgentPipeline';
import { MorningBrief } from './components/MorningBrief';
import { useDeals } from './hooks/useDeals';
import { useEvaContext } from './hooks/useEvaContext';
import type { ApiStatus } from './types';

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

/* ─────────────────────────────────────────
   NAV STRUCTURE
   Group → Section → id
───────────────────────────────────────── */
type NavId =
  | 'command'
  | 'acquire'
  | 'distribute'
  | 'intel'
  | 'incubator'
  | 'roadmap'
  | 'portfolio'
  | 'myday'
  | 'energy'
  | 'glossai'
  | 'agents'
  | 'settings';

interface NavItem {
  id: NavId;
  icon: string;   // lucide-style SVG path OR emoji fallback
  label: string;
  group: 'business' | 'personal' | 'system';
  badge?: number;
}

const NAV_ITEMS: NavItem[] = [
  // BUSINESS
  { id: 'command',    icon: '⚡', label: 'Command',    group: 'business' },
  { id: 'acquire',    icon: '🎯', label: 'Acquire',    group: 'business', badge: 2 },
  { id: 'distribute', icon: '📡', label: 'Distribute', group: 'business' },
  { id: 'intel',      icon: '🧠', label: 'Intel',      group: 'business' },
  { id: 'incubator',  icon: '🌱', label: 'Incubator',  group: 'business' },
  { id: 'roadmap',    icon: '🗺️', label: 'Roadmap',    group: 'business' },
  { id: 'portfolio',  icon: '📊', label: 'Portfolio',  group: 'business' },
  // PERSONAL
  { id: 'myday',      icon: '🌅', label: 'My Day',     group: 'personal' },
  { id: 'energy',     icon: '🔋', label: 'Energy',     group: 'personal' },
  { id: 'glossai',    icon: '✨', label: 'GLŌSSAI',    group: 'personal' },
  // SYSTEM
  { id: 'agents',     icon: '🤖', label: 'Agents',     group: 'system' },
  { id: 'settings',   icon: '⚙️', label: 'Settings',   group: 'system' },
];

const GROUP_LABELS: Record<string, string> = {
  business: 'Business',
  personal: 'Personal',
  system:   'System',
};

const SERVICE_PORTS = [
  { port: ':8766', label: 'Deal Scout' },
  { port: ':8767', label: 'Content Engine' },
  { port: ':8768', label: 'Launcher' },
  { port: ':8770', label: 'Channels Hub' },
  { port: ':8771', label: 'Knowledge OS' },
  { port: ':8773', label: 'Pathfinder' },
];

function useServiceStatus(ports: { port: string; label: string }[]) {
  const [statuses, setStatuses] = useState<Record<string, boolean>>({});
  useEffect(() => {
    const portMap: Record<string, number> = {
      ':8766': 8766, ':8767': 8767, ':8768': 8768, ':8770': 8770, ':8771': 8771, ':8773': 8773,
    };
    const check = async () => {
      const results: Record<string, boolean> = {};
      await Promise.all(
        ports.map(async ({ port }) => {
          const num = portMap[port];
          if (!num) { results[port] = false; return; }
          try {
            const r = await fetch(`http://localhost:${num}/health`, { signal: AbortSignal.timeout(1500) });
            results[port] = r.ok;
          } catch { results[port] = false; }
        })
      );
      setStatuses(results);
    };
    check();
    const id = setInterval(check, 30000);
    return () => clearInterval(id);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return statuses;
}

/* ─────────────────────────────────────────
   SIDEBAR NAV
───────────────────────────────────────── */
function NavPanel({ active, onSelect }: { active: NavId; onSelect: (id: NavId) => void }) {
  const statuses = useServiceStatus(SERVICE_PORTS);
  const onlineSvcs = SERVICE_PORTS.filter(p => statuses[p.port]).length;

  const groups = (['business', 'personal', 'system'] as const);

  return (
    <nav
      className="flex flex-col h-full shrink-0"
      style={{
        width: 'var(--nav-width)',
        minWidth: 'var(--nav-width)',
        background: 'var(--bg)',
        boxShadow: '1px 0 0 var(--border)',
      }}
    >
      {/* Wordmark */}
      <div
        className="px-5 py-5"
        style={{ borderBottom: '1px solid var(--border-light)' }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {/* EVA logomark — geometric triangle */}
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-label="EVA">
            <rect width="28" height="28" rx="7" fill="#00C07F" />
            <path d="M14 6L22 20H6L14 6Z" fill="white" fillOpacity="0.95" />
          </svg>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.01em' }}>
              EVA
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-tertiary)', letterSpacing: '0.04em' }}>
              Command Center
            </div>
          </div>
        </div>
      </div>

      {/* Nav groups */}
      <div className="flex-1 overflow-y-auto py-3">
        {groups.map((group, gi) => {
          const items = NAV_ITEMS.filter(n => n.group === group);
          return (
            <div key={group} className={gi > 0 ? 'mt-4' : ''}>
              <div
                className="eva-label px-5 mb-1"
                style={{ paddingTop: 4, paddingBottom: 4 }}
              >
                {GROUP_LABELS[group]}
              </div>
              {items.map(item => {
                const isActive = active === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => onSelect(item.id)}
                    className={`nav-item w-full text-left${isActive ? ' active' : ''}`}
                  >
                    <span style={{ fontSize: 16, lineHeight: 1 }}>{item.icon}</span>
                    <span style={{ flex: 1 }}>{item.label}</span>
                    {item.badge ? (
                      <span
                        className="eva-badge eva-badge-green"
                        style={{ padding: '1px 6px', fontSize: 10 }}
                      >
                        {item.badge}
                      </span>
                    ) : null}
                  </button>
                );
              })}
            </div>
          );
        })}
      </div>

      {/* Services footer */}
      <div
        className="px-5 py-4"
        style={{ borderTop: '1px solid var(--border-light)' }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <div className="eva-label">
            {onlineSvcs}/{SERVICE_PORTS.length} Services
          </div>
          {onlineSvcs === 0 && (
            <span
              title="Run on your Mac: bash ~/Eva/modules/autostart/eva-install-services.sh"
              style={{
                fontSize: 9,
                fontWeight: 700,
                letterSpacing: '0.05em',
                color: '#ff3b30',
                background: 'rgba(255,59,48,0.1)',
                padding: '2px 6px',
                borderRadius: 4,
                cursor: 'default',
              }}
            >
              OFFLINE
            </span>
          )}
        </div>
        <div className="flex flex-col gap-1.5">
          {SERVICE_PORTS.map(({ port, label }) => {
            const online = statuses[port] ?? false;
            return (
              <div key={port} className="flex items-center gap-2">
                <span
                  className={`agent-dot ${online ? 'agent-dot-running' : 'agent-dot-idle'}`}
                />
                <span style={{ fontSize: 11, color: online ? 'var(--accent-dark)' : 'var(--text-tertiary)' }}>
                  {label}
                </span>
              </div>
            );
          })}
        </div>
        {onlineSvcs === 0 && (
          <div style={{
            marginTop: 10,
            padding: '8px 10px',
            background: 'rgba(255,59,48,0.06)',
            border: '1px solid rgba(255,59,48,0.2)',
            borderRadius: 6,
          }}>
            <div style={{ fontSize: 9, fontWeight: 700, color: '#ff3b30', letterSpacing: '0.05em', marginBottom: 4 }}>
              START SERVICES ON MAC
            </div>
            <code style={{ fontSize: 9.5, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', lineHeight: 1.6, display: 'block', wordBreak: 'break-all' }}>
              bash ~/Eva/modules/autostart/eva-install-services.sh
            </code>
          </div>
        )}
      </div>
    </nav>
  );
}

/* ─────────────────────────────────────────
   CONTENT PANE — one view at a time
───────────────────────────────────────── */
interface ContentPaneProps {
  active: NavId;
  pipelineDeals: ReturnType<typeof useDeals>['pipelineDeals'];
  archivedDeals: ReturnType<typeof useDeals>['archivedDeals'];
  allDeals: ReturnType<typeof useDeals>['allDeals'];
  dealsLoading: boolean;
  dealsStatus: ReturnType<typeof useDeals>['status'];
  dealsUpdated: ReturnType<typeof useDeals>['lastUpdated'];
  refreshDeals: () => void;
  advanceStage: ReturnType<typeof useDeals>['advanceStage'];
  archiveDeal: ReturnType<typeof useDeals>['archiveDeal'];
  unarchiveDeal: ReturnType<typeof useDeals>['unarchiveDeal'];
  getDealHistory: ReturnType<typeof useDeals>['getDealHistory'];
  context: ReturnType<typeof useEvaContext>['context'];
  contextLoading: boolean;
  contextStatus: ReturnType<typeof useEvaContext>['status'];
  contextUpdated: ReturnType<typeof useEvaContext>['lastUpdated'];
  refreshContext: () => void;
}

function SectionHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-6">
      <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
        {title}
      </h1>
      {subtitle && (
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>{subtitle}</p>
      )}
    </div>
  );
}

function ContentPane({
  active,
  pipelineDeals, archivedDeals, allDeals,
  dealsLoading, dealsStatus, dealsUpdated, refreshDeals,
  advanceStage, archiveDeal, unarchiveDeal, getDealHistory,
  context, contextLoading, contextStatus, contextUpdated, refreshContext,
}: ContentPaneProps) {
  const [rendered, setRendered] = useState<NavId>(active);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    if (active === rendered) return;
    setVisible(false);
    const t = setTimeout(() => { setRendered(active); setVisible(true); }, 140);
    return () => clearTimeout(t);
  }, [active, rendered]);

  return (
    <main
      className="flex-1 overflow-y-auto"
      style={{ background: 'var(--bg-secondary)', minWidth: 0 }}
    >
      <div
        style={{
          opacity: visible ? 1 : 0,
          transform: visible ? 'translateY(0)' : 'translateY(8px)',
          transition: 'opacity 180ms ease, transform 180ms ease',
          padding: '28px 32px',
          maxWidth: 1200,
          margin: '0 auto',
        }}
      >

        {/* ── COMMAND ── */}
        {rendered === 'command' && (
          <>
            <SectionHeader title="Command" subtitle="What needs to happen today" />
            <div className="space-y-4">
              <MorningBrief />
              <div className="grid grid-cols-2 gap-4">
                <RevenueGauge current={0} target={10000} />
                <PriorityStack />
              </div>
            </div>
          </>
        )}

        {/* ── ACQUIRE ── */}
        {rendered === 'acquire' && (
          <>
            <SectionHeader title="Acquire" subtitle="Deal pipeline · Online businesses · RCFE" />
            <div className="space-y-4">
              <DealScoutView />
              <DealTracker
                pipelineDeals={pipelineDeals}
                archivedDeals={archivedDeals}
                allDeals={allDeals}
                loading={dealsLoading}
                status={dealsStatus}
                lastUpdated={dealsUpdated}
                onRefresh={refreshDeals}
                onAdvanceStage={advanceStage}
                onArchive={archiveDeal}
                onUnarchive={unarchiveDeal}
                onGetHistory={getDealHistory}
              />
            </div>
          </>
        )}

        {/* ── DISTRIBUTE ── */}
        {rendered === 'distribute' && (
          <>
            <SectionHeader title="Distribute" subtitle="Channels · Social queue · Content" />
            <div className="space-y-4">
              <ChannelsHub />
              <SocialQueue />
              <ContentQueue />
            </div>
          </>
        )}

        {/* ── INTEL ── */}
        {rendered === 'intel' && (
          <>
            <SectionHeader title="Intel" subtitle="Market signals · Activity" />
            <div className="space-y-4">
              <SocialSignals />
              <ActivityFeed
                context={context}
                loading={contextLoading}
                status={contextStatus}
                lastUpdated={contextUpdated}
                onRefresh={refreshContext}
              />
            </div>
          </>
        )}

        {/* ── MY DAY ── */}
        {rendered === 'myday' && (
          <>
            <SectionHeader title="My Day" subtitle="Schedule · Reminders · Priorities" />
            <div className="space-y-4">
              <WellnessBlocks />
              <RemindersPanel />
              <PriorityRoadmap />
            </div>
          </>
        )}

        {/* ── ENERGY ── */}
        {rendered === 'energy' && (
          <>
            <SectionHeader title="Energy" subtitle="Daily energy budget · Action queue" />
            <div className="space-y-4">
              <EnergyBudget />
              <ActionQueue />
            </div>
          </>
        )}

        {/* ── AGENTS ── */}
        {rendered === 'agents' && (
          <>
            <SectionHeader title="Agents" subtitle="EVA's autonomous workers" />
            <div className="space-y-4">
              <AgentPipeline />
            </div>
          </>
        )}

        {/* ── ROADMAP ── */}
        {rendered === 'roadmap' && (
          <>
            <SectionHeader title="Mission Roadmap" subtitle="30-day sprint · June 25 deadline · $10K MRR + deal closed" />
            <MissionRoadmap />
          </>
        )}

        {/* ── PORTFOLIO ── */}
        {rendered === 'portfolio' && (
          <>
            <SectionHeader title="Portfolio Map" subtitle="Revenue streams · Project categories · At-a-glance dashboard" />
            <PortfolioMap />
          </>
        )}

        {/* ── INCUBATOR ── */}
        {rendered === 'incubator' && (
          <>
            <SectionHeader title="Incubator" subtitle="Pathfinder pipeline · Waitlist leads · Outreach" />
            <div className="space-y-4">
              <PathfinderLeads />
              <IncubationPanel />
            </div>
          </>
        )}

        {/* ── GLŌSSAI ── */}
        {rendered === 'glossai' && (
          <>
            <SectionHeader title="GLŌSSAI" subtitle="Organic beauty · Inside-out wellness · Skin intelligence" />
            <div className="space-y-4">
              <GlossaiPanel />
            </div>
          </>
        )}

        {/* ── SETTINGS ── */}
        {rendered === 'settings' && (
          <>
            <SectionHeader title="Settings" subtitle="Terminal · Channels · Config" />
            <div className="space-y-4">
              <TerminalPanel />
              <ChannelsHub />
            </div>
          </>
        )}

      </div>
    </main>
  );
}

/* ─────────────────────────────────────────
   DASHBOARD
───────────────────────────────────────── */
function Dashboard() {
  const [activeNav, setActiveNav] = useState<NavId>('command');

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

  const apiStatus: ApiStatus = {
    dealScout: dealsStatus,
    evaContext: contextStatus,
  };

  const handleRefreshAll = useCallback(() => {
    refreshDeals();
    refreshContext();
  }, [refreshDeals, refreshContext]);

  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--bg)' }}>
      {/* Top bar */}
      <CommandHeader apiStatus={apiStatus} onRefreshAll={handleRefreshAll} />

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        <NavPanel active={activeNav} onSelect={setActiveNav} />
        <ContentPane
          active={activeNav}
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
      </div>

      {/* Footer */}
      <footer
        className="px-6 py-2 flex items-center justify-between shrink-0"
        style={{ borderTop: '1px solid var(--border-light)', background: 'var(--bg)' }}
      >
        <span style={{ fontSize: 11, color: 'var(--text-tertiary)', letterSpacing: '0.02em' }}>
          EVA v0.8.2 · Mangotec LLC
        </span>
        <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
          Personal & Business OS
        </span>
      </footer>
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
