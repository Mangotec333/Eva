import { useState, useEffect, useRef, useCallback, KeyboardEvent } from 'react';

interface OutputLine {
  id: string;
  timestamp: string;
  text: string;
  type: 'output' | 'error' | 'system' | 'command';
}

interface ExecResult {
  stdout: string;
  stderr: string;
  exit_code: number;
  duration_ms: number;
  command: string;
}

interface QuickCommand {
  label: string;
  command: string;
}

const QUICK_COMMANDS: QuickCommand[] = [
  { label: 'git pull', command: 'cd ~/Eva && git pull origin main' },
  { label: 'services status', command: 'launchctl list | grep eva' },
  { label: 'install services', command: 'bash ~/Eva/modules/autostart/eva-install-services.sh' },
  { label: 'content engine', command: 'cd ~/Eva/modules/content-engine && python3 main.py' },
  { label: 'deal scout', command: 'cd ~/Eva/modules/deal-scout && python3 main.py' },
  { label: 'logs: content', command: 'tail -30 ~/Eva/logs/eva-content-engine.error.log' },
  { label: 'logs: deal scout', command: 'tail -30 ~/Eva/logs/eva-deal-scout.error.log' },
  {
    label: 'wire linkedin',
    command: `curl -s -X POST http://localhost:8768/credentials/set -H 'Content-Type: application/json' -d '{"service":"linkedin","credentials":{"username":"","password":""}}'`,
  },
];

const MAX_HISTORY = 20;

function getTimestamp(): string {
  return new Date().toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function makeId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

function makeLine(text: string, type: OutputLine['type']): OutputLine {
  return { id: makeId(), timestamp: getTimestamp(), text, type };
}

const STARTUP_LINES: OutputLine[] = [
  makeLine('EVA TERMINAL — connected to Launcher :8768', 'system'),
  makeLine('Type a command or click a quick-action above.', 'system'),
  makeLine('─────────────────────────────────────────────', 'system'),
];

export function TerminalPanel() {
  const [lines, setLines] = useState<OutputLine[]>(STARTUP_LINES);
  const [input, setInput] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [launcherOnline, setLauncherOnline] = useState(true);
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number>(-1);

  const outputRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom on new output
  useEffect(() => {
    const el = outputRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [lines]);

  const appendLines = useCallback((newLines: OutputLine[]) => {
    setLines(prev => [...prev, ...newLines]);
  }, []);

  const runCommand = useCallback(
    async (command: string) => {
      if (!command.trim() || isRunning) return;

      const trimmed = command.trim();

      // Add command line to output
      appendLines([makeLine(`$ ${trimmed}`, 'command')]);

      // Update history
      setHistory(prev => {
        const next = [trimmed, ...prev.filter(h => h !== trimmed)].slice(0, MAX_HISTORY);
        return next;
      });
      setHistoryIndex(-1);
      setInput('');
      setIsRunning(true);

      try {
        const response = await fetch('http://localhost:8768/terminal/exec', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ command: trimmed, timeout: 30 }),
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const result: ExecResult = await response.json();
        setLauncherOnline(true);

        const newLines: OutputLine[] = [];

        if (result.stdout) {
          result.stdout
            .split('\n')
            .filter(l => l !== '')
            .forEach(l => newLines.push(makeLine(l, 'output')));
        }

        if (result.stderr) {
          result.stderr
            .split('\n')
            .filter(l => l !== '')
            .forEach(l => newLines.push(makeLine(l, 'error')));
        }

        const status =
          result.exit_code === 0
            ? `✓ done (${result.duration_ms}ms)`
            : `✗ exited ${result.exit_code} (${result.duration_ms}ms)`;
        newLines.push(makeLine(status, result.exit_code === 0 ? 'system' : 'error'));

        appendLines(newLines);
      } catch {
        setLauncherOnline(false);
        appendLines([
          makeLine(
            '⚠ Launcher offline — start EVA Launcher on your Mac first',
            'error',
          ),
        ]);
      } finally {
        setIsRunning(false);
        inputRef.current?.focus();
      }
    },
    [isRunning, appendLines],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') {
        runCommand(input);
        return;
      }

      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setHistoryIndex(prev => {
          const next = Math.min(prev + 1, history.length - 1);
          if (history[next] !== undefined) setInput(history[next]);
          return next;
        });
        return;
      }

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setHistoryIndex(prev => {
          const next = prev - 1;
          if (next < 0) {
            setInput('');
            return -1;
          }
          if (history[next] !== undefined) setInput(history[next]);
          return next;
        });
      }
    },
    [input, history, runCommand],
  );

  const handleClear = useCallback(() => {
    setLines([makeLine('─────────────────────────────────────────────', 'system')]);
  }, []);

  const getLineClass = (type: OutputLine['type']): string => {
    switch (type) {
      case 'error':
        return 'text-red-400';
      case 'system':
        return 'text-cyan-400';
      case 'command':
        return 'text-green-300 font-semibold';
      default:
        return 'text-green-400';
    }
  };

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs tracking-widest text-gray-400 uppercase">
            Terminal
          </span>
          <span
            className={`inline-block w-2 h-2 rounded-full ${
              launcherOnline ? 'bg-green-400' : 'bg-gray-600'
            }`}
            title={launcherOnline ? 'Launcher online' : 'Launcher offline'}
          />
        </div>
        <button
          onClick={handleClear}
          className="text-xs font-mono px-2 py-1 rounded bg-gray-800 border border-gray-700 text-gray-400 hover:bg-gray-700 hover:text-gray-200 cursor-pointer transition-colors"
        >
          CLEAR
        </button>
      </div>

      {/* Quick command chips */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        {QUICK_COMMANDS.map(qc => (
          <button
            key={qc.label}
            onClick={() => runCommand(qc.command)}
            disabled={isRunning}
            className="text-xs font-mono px-2 py-1 rounded bg-gray-800 border border-gray-700 text-cyan-400 hover:bg-gray-700 cursor-pointer transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {qc.label}
          </button>
        ))}
      </div>

      {/* Output area */}
      <div
        ref={outputRef}
        className="bg-gray-950 border border-gray-800 rounded-lg overflow-y-auto mb-3"
        style={{ minHeight: '300px', maxHeight: '500px' }}
      >
        <div className="p-3 space-y-0.5">
          {lines.map(line => (
            <div key={line.id} className="flex gap-2 leading-5">
              <span className="text-gray-500 font-mono text-sm select-none shrink-0">
                [{line.timestamp}]
              </span>
              <span className={`font-mono text-sm break-all ${getLineClass(line.type)}`}>
                {line.text}
              </span>
            </div>
          ))}
          {isRunning && (
            <div className="flex gap-2 leading-5">
              <span className="text-gray-500 font-mono text-sm select-none shrink-0">
                [{getTimestamp()}]
              </span>
              <span className="font-mono text-sm text-green-400 animate-pulse">
                running…
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Input row */}
      <div className="flex gap-2 items-center">
        <span className="font-mono text-sm text-green-400 shrink-0">$</span>
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={e => {
            setInput(e.target.value);
            setHistoryIndex(-1);
          }}
          onKeyDown={handleKeyDown}
          disabled={isRunning}
          placeholder="run command on your Mac..."
          className="flex-1 bg-gray-900 border border-gray-700 text-green-400 font-mono text-sm rounded px-3 py-1.5 placeholder-gray-600 focus:outline-none focus:border-cyan-700 disabled:opacity-50 transition-colors"
          autoComplete="off"
          spellCheck={false}
        />
        <button
          onClick={() => runCommand(input)}
          disabled={isRunning || !input.trim()}
          className="px-3 py-1.5 rounded bg-cyan-700 border border-cyan-600 text-white font-mono text-sm hover:bg-cyan-600 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer transition-colors"
          title="Run"
        >
          →
        </button>
      </div>
    </div>
  );
}
