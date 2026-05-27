import { useState } from 'react';
import { DealScoutView } from './DealScoutView';
import { DealTracker } from './DealTracker';
import { MorningBrief } from './MorningBrief';
import { WellnessBlocks } from './WellnessBlocks';
import { ContentQueue } from './ContentQueue';
import { SocialSignals } from './SocialSignals';
import { ActivityFeed } from './ActivityFeed';
import { RevenueGauge } from './RevenueGauge';
import { useDeals } from '../hooks/useDeals';
import { useEvaContext } from '../hooks/useEvaContext';
import type { EvaContextToday } from '../types';

/* ─────────────────────────────────────────
   PROPS
───────────────────────────────────────── */
interface ProjectsViewProps {
  pipelineDeals: ReturnType<typeof useDeals>['pipelineDeals'];
  archivedDeals: ReturnType<typeof useDeals>['archivedDeals'];
  allDeals: ReturnType<typeof useDeals>['allDeals'];
  dealsLoading: boolean;
  dealsStatus: ReturnType<typeof useDeals>['status'];
  dealsUpdated: Date | null;
  refreshDeals: () => void;
  advanceStage: ReturnType<typeof useDeals>['advanceStage'];
  archiveDeal: ReturnType<typeof useDeals>['archiveDeal'];
  unarchiveDeal: ReturnType<typeof useDeals>['unarchiveDeal'];
  getDealHistory: ReturnType<typeof useDeals>['getDealHistory'];
  context: EvaContextToday | null;
  contextLoading: boolean;
  contextStatus: ReturnType<typeof useEvaContext>['status'];
  contextUpdated: Date | null;
  refreshContext: () => void;
}

/* ─────────────────────────────────────────
   ACCORDION SECTION
───────────────────────────────────────── */
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(true);

  return (
    <div style={{
      background: '#111111',
      border: '1px solid #1e1e1e',
      borderRadius: 16,
      overflow: 'hidden',
    }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '16px 20px',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          borderBottom: open ? '1px solid #1e1e1e' : 'none',
        }}
      >
        <span style={{ fontSize: 15, fontWeight: 600, color: '#ffffff' }}>{title}</span>
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="#4b5563"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{ transform: open ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 200ms' }}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      {open && <div style={{ padding: '20px' }}>{children}</div>}
    </div>
  );
}

/* ─────────────────────────────────────────
   ASSEMBLY LINE TABLE
───────────────────────────────────────── */
interface AssemblyItem {
  name: string;
  stage: number;
  waitlist: string;
  spend: string;
  status: 'Active' | 'Paused';
}

const ASSEMBLY_ITEMS: AssemblyItem[] = [
  { name: 'EVA AI Agency', stage: 2, waitlist: '0 leads', spend: '$0', status: 'Active' },
  { name: 'RCFE Deal', stage: 4, waitlist: '—', spend: '$0', status: 'Active' },
  { name: 'GLŌSSAI', stage: 1, waitlist: '0 leads', spend: '$0', status: 'Paused' },
];

const STAGE_COLORS: Record<number, string> = {
  1: '#374151',
  2: '#3b82f6',
  3: '#8b5cf6',
  4: '#f59e0b',
  5: '#22c55e',
};

function StageBadge({ stage }: { stage: number }) {
  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
      {[1, 2, 3, 4, 5].map(n => (
        <div
          key={n}
          style={{
            width: 16,
            height: 16,
            borderRadius: '50%',
            background: n <= stage ? STAGE_COLORS[n] : '#1e1e1e',
            border: `1px solid ${n <= stage ? STAGE_COLORS[n] : '#2a2a2a'}`,
            fontSize: 9,
            color: n <= stage ? '#ffffff' : '#374151',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 700,
          }}
        >
          {n}
        </div>
      ))}
    </div>
  );
}

function AssemblyLine() {
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr>
          {['Idea', 'Stage', 'Waitlist', 'Spend', 'Status'].map(h => (
            <th
              key={h}
              style={{
                textAlign: 'left',
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                color: '#4b5563',
                padding: '0 0 12px 0',
                paddingRight: 24,
              }}
            >
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {ASSEMBLY_ITEMS.map((item, i) => (
          <tr key={i} style={{ borderTop: '1px solid #1a1a1a' }}>
            <td style={{ padding: '12px 24px 12px 0', fontSize: 14, color: '#ffffff', fontWeight: 500 }}>
              {item.name}
            </td>
            <td style={{ padding: '12px 24px 12px 0' }}>
              <StageBadge stage={item.stage} />
            </td>
            <td style={{ padding: '12px 24px 12px 0', fontSize: 13, color: '#9ca3af' }}>
              {item.waitlist}
            </td>
            <td style={{ padding: '12px 24px 12px 0', fontSize: 13, color: '#9ca3af' }}>
              {item.spend}
            </td>
            <td style={{ padding: '12px 0 12px 0' }}>
              <span style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 5,
                fontSize: 11,
                fontWeight: 600,
                padding: '3px 10px',
                borderRadius: 20,
                background: item.status === 'Active' ? 'rgba(6,182,212,0.12)' : '#1e1e1e',
                color: item.status === 'Active' ? '#06b6d4' : '#6b7280',
              }}>
                {item.status}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ─────────────────────────────────────────
   FINANCE SECTION
───────────────────────────────────────── */
function FinanceSection() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <RevenueGauge current={0} target={10000} />
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            {['Item', 'Amount', 'Rate / Note'].map(h => (
              <th
                key={h}
                style={{
                  textAlign: 'left',
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                  color: '#4b5563',
                  padding: '0 0 12px 0',
                  paddingRight: 24,
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {[
            { item: 'HELOC', amount: '$200K', note: '@ 9.5%' },
            { item: 'Monthly service', amount: '$1,682', note: 'per month' },
            { item: 'Runway', amount: '~119 months', note: 'at current burn' },
          ].map((row, i) => (
            <tr key={i} style={{ borderTop: '1px solid #1a1a1a' }}>
              <td style={{ padding: '10px 24px 10px 0', fontSize: 14, color: '#ffffff' }}>{row.item}</td>
              <td style={{ padding: '10px 24px 10px 0', fontSize: 14, color: '#22c55e', fontWeight: 600 }}>{row.amount}</td>
              <td style={{ padding: '10px 0 10px 0', fontSize: 13, color: '#6b7280' }}>{row.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ─────────────────────────────────────────
   PROJECTS VIEW
───────────────────────────────────────── */
export function ProjectsView({
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
}: ProjectsViewProps) {
  return (
    <div style={{ padding: '40px 48px', maxWidth: 1280, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: 28, fontWeight: 600, color: '#ffffff', margin: 0, letterSpacing: '-0.02em' }}>
          Projects
        </h1>
        <p style={{ fontSize: 13, color: '#9ca3af', marginTop: 4 }}>
          Assembly line · Deals · Operations
        </p>
      </div>

      {/* Sections */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

        {/* 1. Assembly Line */}
        <Section title="Assembly Line">
          <AssemblyLine />
        </Section>

        {/* 2. Acquire */}
        <Section title="Acquire">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
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
        </Section>

        {/* 3. Operations */}
        <Section title="Operations">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <MorningBrief />
            <WellnessBlocks />
            <ContentQueue />
          </div>
        </Section>

        {/* 4. Intelligence */}
        <Section title="Intelligence">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <SocialSignals />
            <ActivityFeed
              context={context}
              loading={contextLoading}
              status={contextStatus}
              lastUpdated={contextUpdated}
              onRefresh={refreshContext}
            />
          </div>
        </Section>

        {/* 5. Finance */}
        <Section title="Finance">
          <FinanceSection />
        </Section>

      </div>
    </div>
  );
}

export default ProjectsView;
