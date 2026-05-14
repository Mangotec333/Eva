import { TrendingUp, ArrowUp, DollarSign } from 'lucide-react';

interface RevenueGaugeProps {
  current?: number;
  target?: number;
}

const THRESHOLD = 10_000;

function formatCurrency(n: number): string {
  if (n >= 1000) return `$${(n / 1000).toFixed(1)}K`;
  return `$${n.toLocaleString()}`;
}

interface BreakdownItem {
  label: string;
  value: number;
  color: string;
}

export function RevenueGauge({ current = 0, target = THRESHOLD }: RevenueGaugeProps) {
  const pct = Math.min((current / target) * 100, 100);
  const gap = Math.max(target - current, 0);

  const breakdown: BreakdownItem[] = [
    { label: 'Acquisition Target', value: 9800, color: 'text-cyan-400' },
    { label: 'Agency', value: 0, color: 'text-amber-400' },
    { label: 'Total', value: current, color: 'text-green-400' },
  ];

  // Determine gauge color based on progress
  const gaugeColor =
    pct >= 80 ? 'from-green-500 to-green-400' :
    pct >= 50 ? 'from-cyan-500 to-cyan-400' :
    pct >= 20 ? 'from-amber-500 to-amber-400' :
    'from-red-500 to-red-400';

  const textColor =
    pct >= 80 ? 'text-green-400' :
    pct >= 50 ? 'text-cyan-400' :
    pct >= 20 ? 'text-amber-400' :
    'text-red-400';

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <DollarSign className="w-4 h-4 text-green-400" />
          <span className="font-mono text-xs font-bold text-gray-400 tracking-widest uppercase">
            Revenue Gauge
          </span>
        </div>
        <div className="flex items-center gap-1 px-2 py-0.5 bg-amber-500/10 border border-amber-500/30 rounded">
          <ArrowUp className="w-3 h-3 text-amber-400" />
          <span className="font-mono text-xs text-amber-400 font-semibold">
            ARROW FLIPS AT $10K/mo
          </span>
        </div>
      </div>

      {/* Big Number */}
      <div className="flex items-end gap-3">
        <div>
          <div className={`font-mono text-5xl font-bold ${textColor} tabular-nums leading-none`}>
            {formatCurrency(current)}
          </div>
          <div className="font-mono text-xs text-gray-500 mt-1">
            / {formatCurrency(target)} target
          </div>
        </div>
        <div className="mb-1 pb-0.5">
          <TrendingUp className={`w-8 h-8 ${textColor} opacity-40`} />
        </div>
      </div>

      {/* Progress Bar */}
      <div className="space-y-1">
        <div className="flex justify-between items-center">
          <span className="font-mono text-xs text-gray-500">
            {pct.toFixed(1)}% of threshold
          </span>
          <span className="font-mono text-xs text-gray-500">
            {formatCurrency(target)}
          </span>
        </div>
        <div className="w-full h-3 bg-gray-800 rounded-full overflow-hidden border border-gray-700">
          <div
            className={`h-full bg-gradient-to-r ${gaugeColor} rounded-full transition-all duration-700 ease-out`}
            style={{ width: `${Math.max(pct, 0.5)}%` }}
          />
        </div>
        {/* Tick marks */}
        <div className="flex justify-between px-0">
          {[0, 25, 50, 75, 100].map(tick => (
            <div key={tick} className="flex flex-col items-center">
              <div className="w-px h-1 bg-gray-700" />
              <span className="font-mono text-[10px] text-gray-600">{tick}%</span>
            </div>
          ))}
        </div>
      </div>

      {/* Breakdown */}
      <div className="border-t border-gray-800 pt-3">
        <div className="grid grid-cols-3 gap-2">
          {breakdown.map(item => (
            <div key={item.label} className="bg-gray-800/60 rounded p-2">
              <div className="font-sans text-[10px] text-gray-500 mb-0.5 uppercase tracking-wide">
                {item.label}
              </div>
              <div className={`font-mono text-sm font-bold ${item.color} tabular-nums`}>
                {formatCurrency(item.value)}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Gap indicator */}
      <div className="flex items-center justify-between bg-gray-800/40 border border-gray-700/50 rounded px-3 py-2">
        <span className="font-mono text-xs text-gray-400">Gap to threshold:</span>
        <span className="font-mono text-sm font-bold text-red-400 tabular-nums">
          -{formatCurrency(gap)}
        </span>
      </div>
    </div>
  );
}
