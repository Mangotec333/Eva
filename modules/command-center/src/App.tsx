import { useCallback } from 'react';
import { CommandHeader } from './components/CommandHeader';
import { RevenueGauge } from './components/RevenueGauge';
import { PriorityStack } from './components/PriorityStack';
import { DealTracker } from './components/DealTracker';
import { EnergyBudget } from './components/EnergyBudget';
import { ActionQueue } from './components/ActionQueue';
import { ActivityFeed } from './components/ActivityFeed';
import { useDeals } from './hooks/useDeals';
import { useEvaContext } from './hooks/useEvaContext';
import type { ApiStatus } from './types';

export default function App() {
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
      {/* Command Header — sticky top bar */}
      <CommandHeader apiStatus={apiStatus} onRefreshAll={handleRefreshAll} />

      {/* Main content grid */}
      <main className="flex-1 p-3 lg:p-4 space-y-3 lg:space-y-4 max-w-[1600px] mx-auto w-full">

        {/* ── Row 1: Revenue Gauge + Priority Stack ── */}
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-3 lg:gap-4">
          {/* Revenue Gauge — top left */}
          <RevenueGauge current={0} target={10000} />

          {/* Priority Stack — top right */}
          <PriorityStack />
        </section>

        {/* ── Row 2: Deal Pipeline (full width) ── */}
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

        {/* ── Row 3: Energy Budget + Action Queue + Activity Feed ── */}
        <section className="grid grid-cols-1 lg:grid-cols-3 gap-3 lg:gap-4">
          {/* Left column: Energy Budget + Action Queue */}
          <div className="lg:col-span-1 flex flex-col gap-3 lg:gap-4">
            <EnergyBudget />
            <ActionQueue />
          </div>

          {/* Right two columns: Activity Feed */}
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

      {/* Footer */}
      <footer className="border-t border-gray-800/50 px-4 py-2 flex items-center justify-between">
        <div className="font-mono text-[10px] text-gray-700 tracking-widest">
          EVA COMMAND CENTER v0.2.0 — MODULE 4
        </div>
        <div className="font-mono text-[10px] text-gray-700">
          DEAL SCOUT :8766 · CONTEXT API :8765
        </div>
      </footer>
    </div>
  );
}
