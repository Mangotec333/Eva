import { useCallback, useState } from 'react';
import { PinGate } from './components/PinGate';
import { CommandHeader } from './components/CommandHeader';
import { RevenueGauge } from './components/RevenueGauge';
import { PriorityStack } from './components/PriorityStack';
import { DealTracker } from './components/DealTracker';
import { EnergyBudget } from './components/EnergyBudget';
import { ActionQueue } from './components/ActionQueue';
import { ActivityFeed } from './components/ActivityFeed';
import { ContentQueue } from './components/ContentQueue';
import { SocialQueue } from './components/SocialQueue';
import RemindersPanel from './components/RemindersPanel';
import { TerminalPanel } from './components/TerminalPanel';
import { ChannelsHub } from './components/ChannelsHub';
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

function Dashboard() {
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
    <div className="min-h-screen bg-gray-950 bg-grid flex flex-col">
      <CommandHeader apiStatus={apiStatus} onRefreshAll={handleRefreshAll} />
      <main className="flex-1 p-3 lg:p-4 space-y-3 lg:space-y-4 max-w-[1600px] mx-auto w-full">
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-3 lg:gap-4">
          <RevenueGauge current={0} target={10000} />
          <PriorityStack />
        </section>
        <section>
          <AgentPipeline />
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
        <section>
          <ContentQueue />
        </section>
        <section>
          <SocialQueue />
        </section>
        <section>
          <RemindersPanel />
        </section>
        <section>
          <TerminalPanel />
        </section>
        <section>
          <ChannelsHub />
        </section>
        <section className="grid grid-cols-1 lg:grid-cols-3 gap-3 lg:gap-4">
          <div className="lg:col-span-1 flex flex-col gap-3 lg:gap-4">
            <EnergyBudget />
            <ActionQueue />
          </div>
          <div className="lg:col-span-2">
            <ActivityFeed
              context={context}
              loading={contextLoading}
              status={contextStatus}
              lastUpdated={contextUpdated}
              onRefresh={refreshContext}
            />
          </div>
        </section>
      </main>
      <footer className="border-t border-gray-800/50 px-4 py-2 flex items-center justify-between">
        <div className="font-mono text-[10px] text-gray-700 tracking-widest">
          EVA COMMAND CENTER v0.3.0 — MODULE 4
        </div>
        <div className="font-mono text-[10px] text-gray-700">
          DEAL SCOUT :8766 · CONTEXT API :8765 · CONTENT ENGINE :8767 · CHANNELS HUB :8770 · KNOWLEDGE OS :8771
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
