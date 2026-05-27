import { Zap } from 'lucide-react';
import type { EnergyBucket } from '../types';

const ENERGY_BUCKETS: EnergyBucket[] = [
  { label: 'EVA Build', percentage: 40, color: 'bg-cyan-500' },
  { label: 'Deal Sourcing', percentage: 30, color: 'bg-amber-500' },
  { label: 'Agency Outreach', percentage: 20, color: 'bg-purple-500' },
  { label: 'Admin', percentage: 10, color: 'bg-gray-500' },
];

const DOT_COLORS: Record<string, string> = {
  'bg-cyan-500': 'bg-cyan-400',
  'bg-amber-500': 'bg-amber-400',
  'bg-purple-500': 'bg-purple-400',
  'bg-gray-500': 'bg-gray-400',
};

function EnergyBar({ bucket }: { bucket: EnergyBucket }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <div className={`w-1.5 h-1.5 rounded-full ${DOT_COLORS[bucket.color] ?? 'bg-gray-400'}`} />
          <span className="font-sans text-xs text-gray-500">{bucket.label}</span>
        </div>
        <span className="font-mono text-xs font-bold text-gray-500 tabular-nums">
          {bucket.percentage}%
        </span>
      </div>
      <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full ${bucket.color} rounded-full`}
          style={{ width: `${bucket.percentage}%` }}
        />
      </div>
    </div>
  );
}

// Stacked bar visualization
function StackedBar({ buckets }: { buckets: EnergyBucket[] }) {
  return (
    <div className="flex w-full h-4 rounded overflow-hidden gap-px">
      {buckets.map(b => (
        <div
          key={b.label}
          className={`${b.color} flex items-center justify-center transition-all duration-500`}
          style={{ width: `${b.percentage}%` }}
          title={`${b.label}: ${b.percentage}%`}
        >
          {b.percentage >= 15 && (
            <span className="font-mono text-[9px] text-white/80 font-bold">
              {b.percentage}%
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

export function EnergyBudget() {
  const totalHours = 8; // Assume 8-hour workday
  const date = new Date();
  const hour = date.getHours();
  // Rough estimation: if before 6pm, show hours remaining
  const endHour = 18;
  const hoursLeft = Math.max(endHour - hour, 0);

  return (
    <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-amber-400" />
          <span className="font-mono text-xs font-bold text-gray-500 tracking-widest uppercase">
            Energy Budget — Today
          </span>
        </div>
        <div className="flex items-center gap-1 text-gray-500">
          <span className="font-mono text-xs">{hoursLeft}h left</span>
        </div>
      </div>

      {/* Stacked bar */}
      <StackedBar buckets={ENERGY_BUCKETS} />

      {/* Individual bars */}
      <div className="space-y-2">
        {ENERGY_BUCKETS.map(bucket => (
          <EnergyBar key={bucket.label} bucket={bucket} />
        ))}
      </div>

      {/* Time allocation */}
      <div className="border-t border-gray-200 pt-2">
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          {ENERGY_BUCKETS.map(b => (
            <div key={b.label} className="flex items-center justify-between">
              <span className="font-sans text-[10px] text-gray-500 truncate">{b.label}</span>
              <span className="font-mono text-[10px] text-gray-500 tabular-nums">
                {((b.percentage / 100) * totalHours).toFixed(1)}h
              </span>
            </div>
          ))}
        </div>
        <p className="font-mono text-[10px] text-gray-400 mt-1.5">
          ◆ Hardcoded allocation — edit in next sprint
        </p>
      </div>
    </div>
  );
}
