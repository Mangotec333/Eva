import { Activity, WifiOff, Clock, RefreshCw, Terminal } from 'lucide-react';
import type { EvaContextToday, ContextActivity } from '../types';

interface ActivityFeedProps {
  context: EvaContextToday | null;
  loading: boolean;
  status: 'online' | 'offline' | 'loading';
  lastUpdated: Date | null;
  onRefresh: () => void;
}

function timeAgo(timestamp: string): string {
  const diff = Date.now() - new Date(timestamp).getTime();
  const secs = Math.floor(diff / 1000);
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return new Date(timestamp).toLocaleDateString();
}

const ACTIVITY_ICONS: Record<string, { icon: string; color: string }> = {
  llm: { icon: '🤖', color: 'text-cyan-400' },
  context: { icon: '📋', color: 'text-blue-400' },
  deal: { icon: '💼', color: 'text-green-400' },
  screen: { icon: '🖥️', color: 'text-purple-400' },
  log: { icon: '📝', color: 'text-amber-400' },
  default: { icon: '◆', color: 'text-gray-500' },
};

function ActivityRow({ activity }: { activity: ContextActivity }) {
  const typeKey = activity.type?.toLowerCase() ?? 'default';
  const iconConfig =
    ACTIVITY_ICONS[typeKey] ??
    Object.entries(ACTIVITY_ICONS).find(([k]) => typeKey.includes(k))?.[1] ??
    ACTIVITY_ICONS.default;

  return (
    <div className="flex items-start gap-2.5 py-2 border-b border-gray-800/50 last:border-0">
      {/* Icon / dot */}
      <div className={`flex-shrink-0 w-5 h-5 flex items-center justify-center mt-0.5 ${iconConfig.color}`}>
        <span className="text-xs">{iconConfig.icon}</span>
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <p className="font-sans text-xs text-gray-300 leading-snug">
            {activity.summary}
          </p>
          <span className="flex-shrink-0 font-mono text-[10px] text-gray-700 whitespace-nowrap">
            {timeAgo(activity.timestamp)}
          </span>
        </div>
        {activity.source && (
          <span className="font-mono text-[10px] text-gray-600 uppercase tracking-wide">
            {activity.source}
          </span>
        )}
      </div>
    </div>
  );
}

function OfflineState({ onRefresh }: { onRefresh: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-8 gap-3">
      <WifiOff className="w-7 h-7 text-red-400/40" />
      <div className="text-center">
        <div className="font-mono text-sm text-red-400/70 font-semibold">
          EVA Context API offline
        </div>
        <div className="font-sans text-xs text-gray-600 mt-1 max-w-[220px] text-center">
          Start your morning sequence to bring the context engine online
        </div>
      </div>

      {/* Morning sequence hint */}
      <div className="w-full bg-gray-800/50 border border-gray-700/50 rounded p-3 mt-1">
        <div className="font-mono text-[10px] text-amber-400 font-semibold mb-2 tracking-wider">
          ◆ MORNING STARTUP SEQUENCE
        </div>
        <div className="space-y-1">
          {[
            'screenpipe start',
            'eva-logger --daemon',
            'eva-context-api --port 8765',
            'eva-morning-os',
          ].map((cmd, i) => (
            <div key={cmd} className="flex items-center gap-2">
              <span className="font-mono text-[10px] text-gray-700">{i + 1}.</span>
              <code className="font-mono text-[10px] text-cyan-400/80 bg-gray-900/60 px-1.5 py-0.5 rounded">
                {cmd}
              </code>
            </div>
          ))}
        </div>
      </div>

      <button
        onClick={onRefresh}
        className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 border border-gray-700 rounded font-mono text-xs text-gray-400 hover:text-gray-200 hover:border-gray-600 transition-colors"
      >
        <RefreshCw className="w-3 h-3" />
        Retry Connection
      </button>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex flex-col gap-2 py-2">
      {[1, 2, 3, 4].map(i => (
        <div key={i} className="flex items-start gap-2.5 py-2">
          <div className="w-5 h-5 bg-gray-800 rounded animate-pulse flex-shrink-0" />
          <div className="flex-1 space-y-1.5">
            <div className="h-3 bg-gray-800 rounded animate-pulse w-full" />
            <div className="h-3 bg-gray-800 rounded animate-pulse w-2/3" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function ActivityFeed({ context, loading, status, lastUpdated, onRefresh }: ActivityFeedProps) {
  const activities = context?.activities ?? [];
  const sessions = context?.sessions;
  const energyLevel = context?.energy_level;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 flex flex-col gap-3 h-full">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-cyan-400" />
          <span className="font-mono text-xs font-bold text-gray-400 tracking-widest uppercase">
            EVA Activity Feed
          </span>
        </div>
        <div className="flex items-center gap-2">
          {lastUpdated && status === 'online' && (
            <div className="flex items-center gap-1 text-gray-700">
              <Clock className="w-3 h-3" />
              <span className="font-mono text-[10px]">
                {lastUpdated.toLocaleTimeString('en-US', {
                  hour12: false,
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </span>
            </div>
          )}
          <button
            onClick={onRefresh}
            className="p-1 text-gray-600 hover:text-cyan-400 transition-colors"
            title="Refresh context"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Context summary bar (if online) */}
      {status === 'online' && context && (
        <div className="flex items-center gap-4 px-3 py-2 bg-gray-800/50 border border-gray-700/50 rounded">
          <div className="flex items-center gap-1.5">
            <Terminal className="w-3 h-3 text-cyan-400" />
            <span className="font-mono text-xs text-gray-300">
              {context.focus ?? 'No focus set'}
            </span>
          </div>
          {sessions !== undefined && (
            <div className="flex items-center gap-1">
              <span className="font-sans text-[10px] text-gray-600">Sessions:</span>
              <span className="font-mono text-xs text-cyan-400 font-bold">{sessions}</span>
            </div>
          )}
          {energyLevel !== undefined && (
            <div className="flex items-center gap-1">
              <span className="font-sans text-[10px] text-gray-600">Energy:</span>
              <span className={`font-mono text-xs font-bold ${
                energyLevel >= 7 ? 'text-green-400' :
                energyLevel >= 4 ? 'text-amber-400' :
                'text-red-400'
              }`}>{energyLevel}/10</span>
            </div>
          )}
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {status === 'offline' ? (
          <OfflineState onRefresh={onRefresh} />
        ) : loading && activities.length === 0 ? (
          <LoadingState />
        ) : activities.length > 0 ? (
          <div className="flex flex-col">
            {activities.map((activity) => (
              <ActivityRow key={activity.id ?? activity.timestamp} activity={activity} />
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-8 gap-2">
            <Activity className="w-6 h-6 text-gray-700" />
            <span className="font-mono text-xs text-gray-600">No activity recorded today</span>
          </div>
        )}
      </div>

      {/* Summary if available */}
      {context?.summary && (
        <div className="border-t border-gray-800 pt-2">
          <p className="font-sans text-xs text-gray-500 italic leading-relaxed">
            {context.summary}
          </p>
        </div>
      )}
    </div>
  );
}
