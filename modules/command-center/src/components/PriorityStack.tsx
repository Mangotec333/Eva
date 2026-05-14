import { Layers } from 'lucide-react';
import type { Priority, PriorityStatus } from '../types';

const PRIORITIES: Priority[] = [
  {
    rank: 1,
    name: 'EVA Morning OS',
    status: 'ACTIVE - BUILDING',
    description: 'AI operating system — daily startup sequence, context capture, intelligence layer',
  },
  {
    rank: 2,
    name: 'AI Growth Agency',
    status: '90-DAY TARGET',
    description: 'Productized AI services for SMBs — pipeline from EVA outputs',
  },
  {
    rank: 3,
    name: 'Wife & Family',
    status: 'PROTECTED',
    description: 'Non-negotiable protected time — quality over quantity',
  },
  {
    rank: 4,
    name: 'Public Speaking',
    status: 'QUEUED',
    description: 'Keynote & workshop track — activate once agency hits $5K MRR',
  },
  {
    rank: 5,
    name: 'Storeys',
    status: 'BACKGROUND',
    description: 'Real estate / BRRRR portfolio — passive execution, no active time',
  },
  {
    rank: 6,
    name: 'Pureplate',
    status: 'BACKGROUND',
    description: 'Meal prep brand — maintenance mode, no new investment',
  },
];

const STATUS_CONFIG: Record<
  PriorityStatus,
  { bg: string; text: string; border: string; dot: string }
> = {
  'ACTIVE - BUILDING': {
    bg: 'bg-cyan-500/10',
    text: 'text-cyan-400',
    border: 'border-cyan-500/30',
    dot: 'bg-cyan-400',
  },
  '90-DAY TARGET': {
    bg: 'bg-amber-500/10',
    text: 'text-amber-400',
    border: 'border-amber-500/30',
    dot: 'bg-amber-400',
  },
  PROTECTED: {
    bg: 'bg-green-500/10',
    text: 'text-green-400',
    border: 'border-green-500/30',
    dot: 'bg-green-400',
  },
  QUEUED: {
    bg: 'bg-blue-500/10',
    text: 'text-blue-400',
    border: 'border-blue-500/30',
    dot: 'bg-blue-400',
  },
  BACKGROUND: {
    bg: 'bg-gray-700/20',
    text: 'text-gray-500',
    border: 'border-gray-700/40',
    dot: 'bg-gray-500',
  },
  PAUSED: {
    bg: 'bg-red-500/10',
    text: 'text-red-400',
    border: 'border-red-500/30',
    dot: 'bg-red-400',
  },
};

function PriorityCard({ priority }: { priority: Priority }) {
  const config = STATUS_CONFIG[priority.status] ?? STATUS_CONFIG['BACKGROUND'];
  const isActive = priority.status === 'ACTIVE - BUILDING';
  const isBackground = priority.status === 'BACKGROUND';

  return (
    <div
      className={`flex items-center gap-3 px-3 py-2 rounded border transition-colors
        ${isActive
          ? 'bg-cyan-500/5 border-cyan-500/20 hover:bg-cyan-500/10'
          : isBackground
          ? 'bg-gray-800/30 border-gray-800/60 hover:bg-gray-800/50'
          : 'bg-gray-800/60 border-gray-700/60 hover:bg-gray-800'}
      `}
    >
      {/* Rank */}
      <div
        className={`flex-shrink-0 w-6 h-6 rounded flex items-center justify-center
          font-mono text-xs font-bold
          ${isActive ? 'bg-cyan-500/20 text-cyan-400' : 'bg-gray-700/50 text-gray-500'}
        `}
      >
        {priority.rank}
      </div>

      {/* Name + Description */}
      <div className="flex-1 min-w-0">
        <div
          className={`font-mono text-sm font-semibold leading-none mb-0.5 truncate
            ${isBackground ? 'text-gray-500' : 'text-gray-200'}
          `}
        >
          {priority.name}
        </div>
        <div className="font-sans text-xs text-gray-600 truncate">
          {priority.description}
        </div>
      </div>

      {/* Status Pill */}
      <div
        className={`flex-shrink-0 flex items-center gap-1 px-2 py-0.5 rounded border text-xs font-mono font-semibold
          ${config.bg} ${config.text} ${config.border}
        `}
      >
        <div className={`w-1.5 h-1.5 rounded-full ${config.dot} ${isActive ? 'animate-pulse' : ''}`} />
        {priority.status}
      </div>
    </div>
  );
}

export function PriorityStack() {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Layers className="w-4 h-4 text-cyan-400" />
        <span className="font-mono text-xs font-bold text-gray-400 tracking-widest uppercase">
          Life Priority Stack
        </span>
        <span className="ml-auto font-mono text-xs text-gray-600">
          {PRIORITIES.length} PRIORITIES
        </span>
      </div>

      {/* Priority Cards */}
      <div className="flex flex-col gap-1.5">
        {PRIORITIES.map(p => (
          <PriorityCard key={p.rank} priority={p} />
        ))}
      </div>

      {/* Footer note */}
      <div className="border-t border-gray-800 pt-2">
        <p className="font-mono text-[10px] text-gray-600">
          ◆ Focus flows top-down. Lower ranks receive time only after higher ranks are satisfied.
        </p>
      </div>
    </div>
  );
}
