import { useState } from 'react';
import { CheckSquare, Square, ExternalLink, ChevronRight, Play, Loader2 } from 'lucide-react';
import type { Action, ActionTag } from '../types';

const INITIAL_ACTIONS: Action[] = [
  {
    id: 1,
    tag: 'REVENUE',
    text: 'Send 10 DMs to ETA searchers — DealScout $49/mo first customer',
    url: 'https://www.linkedin.com/search/results/people/?keywords=ETA%20searcher%20acquisition',
    completed: false,
  },
  {
    id: 2,
    tag: 'REVENUE',
    text: 'Call Oxnard RCFE broker — verify license transferability + request 3yr P&L',
    url: 'https://www.bizbuysell.com/california/assisted-living-and-nursing-homes-for-sale/',
    completed: false,
    command: undefined,
  },
  {
    id: 3,
    tag: 'BUILD',
    text: 'Boot all EVA services',
    url: undefined,
    command: 'bash ~/Eva/modules/autostart/eva-install-services.sh',
    completed: false,
  },
  {
    id: 4,
    tag: 'BUILD',
    text: 'Start Yaksha — run today\'s money move',
    url: undefined,
    command: 'bash ~/Eva/modules/angels/angel3_monetization/run_angel3.sh',
    completed: false,
  },
  {
    id: 5,
    tag: 'REVIEW',
    text: 'Check LinkedIn ad results — SCOUT + OPERATOR keyword hits',
    url: 'https://www.linkedin.com/campaignmanager/',
    completed: false,
  },
];

const TAG_CONFIG: Record<ActionTag, { bg: string; text: string; border: string }> = {
  REVENUE: {
    bg: 'bg-green-500/10',
    text: 'text-green-400',
    border: 'border-green-500/30',
  },
  BUILD: {
    bg: 'bg-cyan-500/10',
    text: 'text-cyan-400',
    border: 'border-cyan-500/30',
  },
  ADMIN: {
    bg: 'bg-gray-200/20',
    text: 'text-gray-500',
    border: 'border-gray-300/30',
  },
  HEALTH: {
    bg: 'bg-purple-500/10',
    text: 'text-purple-400',
    border: 'border-purple-500/30',
  },
  REVIEW: {
    bg: 'bg-amber-500/10',
    text: 'text-amber-400',
    border: 'border-amber-500/30',
  },
};

async function runCommand(command: string): Promise<void> {
  try {
    await fetch('http://localhost:8768/terminal/exec', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command }),
    });
  } catch {
    // Launcher offline — command shown but not executed
  }
}

function ActionItem({
  action,
  index,
  onToggle,
}: {
  action: Action & { command?: string };
  index: number;
  onToggle: (id: number) => void;
}) {
  const [running, setRunning] = useState(false);
  const tagConfig = TAG_CONFIG[action.tag];

  return (
    <div
      className={`flex items-start gap-3 px-3 py-2.5 rounded border transition-all duration-200
        ${action.completed
          ? 'bg-gray-100/20 border-gray-200/40 opacity-50'
          : 'bg-gray-100/60 border-gray-200/60 hover:bg-gray-100 hover:border-gray-300/80'}
      `}
    >
      {/* Priority number */}
      <div className="flex-shrink-0 w-5 h-5 flex items-center justify-center mt-0.5">
        <span
          className={`font-mono text-xs font-bold ${
            action.completed ? 'text-gray-400' : 'text-gray-500'
          }`}
        >
          {index + 1}
        </span>
      </div>

      {/* Checkbox */}
      <button
        onClick={() => onToggle(action.id)}
        className={`flex-shrink-0 mt-0.5 transition-colors ${
          action.completed
            ? 'text-green-500'
            : 'text-gray-500 hover:text-cyan-400'
        }`}
        aria-label={action.completed ? 'Mark incomplete' : 'Mark complete'}
      >
        {action.completed ? (
          <CheckSquare className="w-4 h-4" />
        ) : (
          <Square className="w-4 h-4" />
        )}
      </button>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-start gap-2 flex-wrap">
          {/* Tag pill */}
          <span
            className={`flex-shrink-0 px-1.5 py-0.5 rounded border font-mono text-[10px] font-bold
              ${tagConfig.bg} ${tagConfig.text} ${tagConfig.border}
            `}
          >
            {action.tag}
          </span>

          {/* Action text */}
          <span
            className={`font-sans text-sm leading-snug ${
              action.completed ? 'line-through text-gray-500' : 'text-gray-800'
            }`}
          >
            {action.text}
          </span>
        </div>

        {/* URL Link */}
        {action.url && !action.completed && (
          <a
            href={action.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 mt-1 font-mono text-[10px] text-cyan-500/70 hover:text-cyan-400 transition-colors"
          >
            <ExternalLink className="w-3 h-3" />
            {action.url.replace(/^https?:\/\//, '')}
          </a>
        )}
      </div>

      {/* Play button for runnable commands */}
      {!action.completed && action.command && (
        <button
          onClick={async () => {
            setRunning(true);
            await runCommand(action.command!);
            setTimeout(() => setRunning(false), 2000);
          }}
          className="flex-shrink-0 mt-0.5 p-1 rounded text-gray-500 hover:text-[#00ff88] hover:bg-[#00ff8815] transition-all"
          title={`Run: ${action.command}`}
        >
          {running
            ? <Loader2 className="w-3.5 h-3.5 animate-spin text-[#00ff88]" />
            : <Play className="w-3.5 h-3.5" fill="currentColor" />}
        </button>
      )}
      {/* Arrow for non-runnable */}
      {!action.completed && !action.command && (
        <ChevronRight className="w-4 h-4 text-gray-400 flex-shrink-0 mt-0.5" />
      )}
    </div>
  );
}

export function ActionQueue() {
  const [actions, setActions] = useState<Action[]>(INITIAL_ACTIONS);

  const toggle = (id: number) => {
    setActions(prev =>
      prev.map(a => (a.id === id ? { ...a, completed: !a.completed } : a))
    );
  };

  const completedCount = actions.filter(a => a.completed).length;
  const totalCount = actions.length;

  return (
    <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <CheckSquare className="w-4 h-4 text-green-400" />
          <span className="font-mono text-xs font-bold text-gray-500 tracking-widest uppercase">
            Action Queue
          </span>
          <span className="font-mono text-xs text-gray-500">
            — TOP {totalCount} LEVERAGE
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="font-mono text-xs text-gray-500">
            {completedCount}/{totalCount}
          </div>
          <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-green-400 rounded-full transition-all duration-300"
              style={{ width: `${(completedCount / totalCount) * 100}%` }}
            />
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex flex-col gap-1.5">
        {actions.map((action, i) => (
          <ActionItem
            key={action.id}
            action={action}
            index={i}
            onToggle={toggle}
          />
        ))}
      </div>

      {/* Completed badge */}
      {completedCount === totalCount && (
        <div className="flex items-center justify-center py-2 bg-green-500/10 border border-green-500/20 rounded">
          <span className="font-mono text-xs text-green-400 font-bold tracking-widest">
            ✓ ALL ACTIONS COMPLETE
          </span>
        </div>
      )}

      {/* Footer */}
      <p className="font-mono text-[10px] text-gray-400">
        ◆ State resets on refresh. Persistent task tracking → next sprint.
      </p>
    </div>
  );
}
