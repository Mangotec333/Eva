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
import { AgentPipeline } from './components/AgentPipeline';
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

type NavCategory = 'command' | 'intelligence' | 'acquisition' | 'distribution' | 'operations';

interface NavItem {
  id: NavCategory;
  icon: string;
  label: string;
  modules: number;
}

const NAV_ITEMS: NavItem[] = [
  { id: 'command',      icon: '⚡', label: 'COMMAND',      modules: 2 },
  { id: 'intelligence', icon: '🧠', label: 'INTELLIGENCE', modules: 3 },
  { id: 'acquisition',  icon: '🎯', label: 'ACQUISITION',  modules: 2 },
  { id: 'distribution', icon: '📡', label: 'DISTRIBUTION', modules: 3 },
  { id: 'operations',   icon: '⚙️', label: 'OPERATIONS',   modules: 4 },
];

const SERVICE_PORTS = [
  { port: ':8766', label: 'Deal Scout' },
  { port: ':8767', label: 'Content Engine' },
  { port: ':8768', label: 'Launcher' },
  { port: ':8770', label: 'Channels Hub' },
  { port: ':8771', label: 'Knowledge OS' },
];

function useServiceStatus(ports: { port: string; label: string }[]) {
  const [statuses, setStatuses] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const portNumbers: Record<string, number> = {
      ':8766': 8766,
      ':8767': 8767,
      ':8768': 8768,
      ':8770': 8770,
      ':8771': 8771,
    };

    const check = async () => {
      const results: Record<string, boolean> = {};
      await Promise.all(
        ports.map(async ({ port }) => {
          const num = portNumbers[port];
          if (!num) { results[port] = false; return; }
          try {
            const r = await fetch(`http://localhost:${num}/health`, {
              signal: AbortSignal.timeout(1500),
            });
            results[port] = r.ok;
          } catch {
            results[port] = false;
          }
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

interface NavPanelProps {
  active: NavCategory;
  onSelect: (cat: NavCategory) => void;
}

function NavPanel({ active, onSelect }: NavPanelProps) {
  const statuses = useServiceStatus(SERVICE_PORTS);

  return (
    <nav
      className="flex flex-col h-full shrink-0 border-r"
      style={{
        width: 200,
        minWidth: 200,
        background: '#0d0d0d',
        borderColor: '#e2e8f0',
      }}
    >
      {/* Wordmark */}
      <div className="px-4 py-4 border-b" style={{ borderColor: '#e2e8f0' }}>
        <div
          className="font-mono font-bold tracking-widest"
          style={{ color: '#00ff88', fontSize: 20, lineHeight: 1 }}
        >
          EVA
        </div>
        <div
          className="font-mono tracking-widest mt-0.5"
          style={{ color: '#444', fontSize: 9 }}
        >
          COMMAND CENTER
        </div>
      </div>

      {/* Nav items */}
      <div className="flex-1 py-2">
        {NAV_ITEMS.map((item) => {
          const isActive = active === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onSelect(item.id)}
              className="w-full text-left px-4 py-2.5 flex flex-col gap-0.5 transition-colors cursor-pointer"
              style={{
                borderLeft: isActive ? '3px solid #00ff88' : '3px solid transparent',
                background: isActive ? '#00ff8808' : 'transparent',
              }}
            >
              <div
                className="flex items-center gap-2 font-mono text-xs font-semibold tracking-wider"
                style={{ color: isActive ? '#00ff88' : '#888' }}
              >
                <span style={{ fontSize: 13 }}>{item.icon}</span>
                <span style={{ fontSize: 12 }}>{item.label}</span>
              </div>
              <div
                className="font-mono pl-5"
                style={{ fontSize: 10, color: '#444' }}
              >
                {item.modules} modules
              </div>
            </button>
          );
        })}
      </div>

      {/* Service status */}
      <div
        className="px-4 py-3 border-t"
        style={{ borderColor: '#e2e8f0' }}
      >
        <div
          className="font-mono mb-2"
          style={{ fontSize: 9, color: '#444', letterSpacing: '0.1em' }}
        >
          5 SERVICES
        </div>
        <div className="flex flex-col gap-1.5">
          {SERVICE_PORTS.map(({ port }) => {
            const online = statuses[port] ?? false;
            return (
              <div key={port} className="flex items-center gap-2">
                <span
                  className="rounded-full shrink-0"
                  style={{
                    width: 6,
                    height: 6,
                    background: online ? '#00ff88' : '#444',
                    boxShadow: online ? '0 0 4px #00ff8866' : 'none',
                  }}
                  title={`${port} — ${online ? 'online' : 'offline'}`}
                />
                <span
                  className="font-mono"
                  style={{ fontSize: 10, color: online ? '#00ff8888' : '#444' }}
                >
                  {port}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </nav>
  );
}

interface ContentPaneProps {
  active: NavCategory;
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

function ContentPane({
  active,
  pipelineDeals,
  archivedDeals,
  allDeals,
  dealsLoading,
  dealsStatus,
  dealsUpdated,
  refreshDeals,
  advanceStage,
  archiveDeal,
  unarchiveDeal,
  getDealHistory,
  context,
  contextLoading,
  contextStatus,
  contextUpdated,
  refreshContext,
}: ContentPaneProps) {
  const [rendered, setRendered] = useState<NavCategory>(active);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    if (active === rendered) return;
    setVisible(false);
    const t = setTimeout(() => {
      setRendered(active);
      setVisible(true);
    }, 150);
    return () => clearTimeout(t);
  }, [active, rendered]);

  return (
    <main
      className="flex-1 overflow-y-auto p-3 lg:p-4"
      style={{ minWidth: 0 }}
    >
      <div
        style={{
          opacity: visible ? 1 : 0,
          transform: visible ? 'translateY(0)' : 'translateY(6px)',
          transition: 'opacity 200ms ease, transform 200ms ease',
        }}
      >
        {rendered === 'command' && (
          <div className="space-y-3 lg:space-y-4 max-w-[1400px] mx-auto">
            <section className="grid grid-cols-1 lg:grid-cols-2 gap-3 lg:gap-4">
              <RevenueGauge current={0} target={10000} />
              <PriorityStack />
            </section>
          </div>
        )}

        {rendered === 'intelligence' && (
          <div className="space-y-3 lg:space-y-4 max-w-[1400px] mx-auto">
            <section>
              <SocialSignals />
            <IncubationPanel />
            </section>
            <section>
              <AgentPipeline />
            </section>
            <section>
              <ActivityFeed
                context={context}
                loading={contextLoading}
                status={contextStatus}
                lastUpdated={contextUpdated}
                onRefresh={refreshContext}
              />
            </section>
          </div>
        )}

        {rendered === 'acquisition' && (
          <div className="space-y-3 lg:space-y-4 max-w-[1400px] mx-auto">
            <section>
              <DealScoutView />
            </section>
            <section>
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
            </section>
          </div>
        )}

        {rendered === 'distribution' && (
          <div className="space-y-3 lg:space-y-4 max-w-[1400px] mx-auto">
            <section>
              <ChannelsHub />
            </section>
            <section>
              <SocialQueue />
            </section>
            <section>
              <ContentQueue />
            </section>
          </div>
        )}

        {rendered === 'operations' && (
          <div className="space-y-3 lg:space-y-4 max-w-[1400px] mx-auto">
            <section>
              <TerminalPanel />
            </section>
            <section>
              <RemindersPanel />
            </section>
            <section className="grid grid-cols-1 lg:grid-cols-2 gap-3 lg:gap-4">
              <EnergyBudget />
              <ActionQueue />
              <PriorityRoadmap />
            </section>
          </div>
        )}
      </div>
    </main>
  );
}

function Dashboard() {
  const [activeNav, setActiveNav] = useState<NavCategory>('command');

  const {
    pipelineDeals,
    archivedDeals,
    allDeals,
    loading: dealsLoading,
    status: dealsStatus,
    lastUpdated: dealsUpdated,
    refresh: refreshDeals,
    advanceStage,
    archiveDeal,
    unarchiveDeal,
    getDealHistory,
  } = useDeals();

  const {
    context,
    loading: contextLoading,
    status: contextStatus,
    lastUpdated: contextUpdated,
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
    <div className="min-h-screen bg-white bg-white flex flex-col">
      {/* Top bar — full width */}
      <CommandHeader apiStatus={apiStatus} onRefreshAll={handleRefreshAll} />

      {/* Nav + Content side by side */}
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

      {/* Footer — full width */}
      <footer className="border-t border-gray-200/50 px-4 py-2 flex items-center justify-between shrink-0">
        <div className="font-mono text-[10px] text-gray-400 tracking-widest">
          EVA COMMAND CENTER v0.4.0 — 5 CATEGORIES · 13 MODULES
        </div>
        <div className="font-mono text-[10px] text-gray-400">
          DEAL SCOUT :8766 · CONTENT ENGINE :8767 · LAUNCHER :8768 · CHANNELS HUB :8770 · KNOWLEDGE OS :8771
        </div>
      </footer>
    </div>
  );
}

export default function App() {
  const [pinPassed, setPinPassed] = useState<boolean>(() => checkPinSession());

  if (!pinPassed) {
    return <PinGate onVerified={() => setPinPassed(true)} />;
  }

  return <Dashboard />;
}
