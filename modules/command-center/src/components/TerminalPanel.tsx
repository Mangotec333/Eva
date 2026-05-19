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

interface BootStep {
  label: string;
  command: string;
  status: 'pending' | 'running' | 'ok' | 'fail' | 'skipped';
}

const BOOT_SEQUENCE: Omit<BootStep, 'status'>[] = [
  { label: 'git pull',          command: 'cd ~/Eva && git pull origin main' },
  { label: 'install deps',      command: 'bash ~/Eva/eva-install-deps.sh' },
  { label: 'install services',  command: 'bash ~/Eva/modules/autostart/eva-install-services.sh' },
  { label: 'services status',   command: 'launchctl list | grep eva' },
  { label: 'port check :8765',  command: 'nc -z localhost 8765 && echo "OPEN" || echo "CLOSED"' },
  { label: 'port check :8766',  command: 'nc -z localhost 8766 && echo "OPEN" || echo "CLOSED"' },
  { label: 'port check :8767',  command: 'nc -z localhost 8767 && echo "OPEN" || echo "CLOSED"' },
];

const QUICK_COMMANDS = [
  { label: 'git pull',          command: 'cd ~/Eva && git pull origin main' },
  { label: 'services status',   command: 'launchctl list | grep eva' },
  { label: 'install services',  command: 'bash ~/Eva/modules/autostart/eva-install-services.sh' },
  { label: 'content engine',    command: 'cd ~/Eva/modules/content-engine && python3 main.py' },
  { label: 'deal scout',        command: 'cd ~/Eva/modules/deal-scout && python3 main.py' },
  { label: 'logs: content',     command: 'tail -30 ~/Eva/logs/eva-content-engine.error.log' },
  { label: 'logs: deal scout',  command: 'tail -30 ~/Eva/logs/eva-deal-scout.error.log' },
  { label: 'wire linkedin',     command: `curl -s -X PUT http://localhost:8767/content/linkedin-config -H 'Content-Type: application/json' -d '{"access_token":"AQU9Fa7kiFqzZWVzWwUhqzH5MNEDQflF07pWFadSNdX8gKgclUwrm4Kc94RbXhKr75PI8OGMAXAtoFO1eZRGq6PdPhW9o_b4QeqjiXe_xDnEmncaxUDq-Yv-_Sle_krMo4E6PQ8cbJwRzi9zI2EQ0cpEkT2kSceHoZ4dmOPGXGP_Dqo77-IUaKze4C5ROrA4Mm9ZkfCoEcpAXC7Y6B8d5kd3kUTWA_ngKyDJUjmdApd_dsPL0TSqyDh_WFpVfW9yvuj6l3qCmM9fg4lo6KZ5ds6cr8XhYqfyFVB-Mvb8nNNVby0ZXxUBIBbidneUgDMJlHkOYbrfkHDrMLbczU_hrSmz_ku3HQ","person_urn":"E_qW9RtfrV"}'` },
];

const MAX_HISTORY = 20;
const LAUNCHER = 'http://localhost:8768';

function ts(): string {
  return new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
function uid(): string { return `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`; }
function line(text: string, type: OutputLine['type']): OutputLine {
  return { id: uid(), timestamp: ts(), text, type };
}

const STARTUP: OutputLine[] = [
  line('EVA TERMINAL — connected to Launcher :8768', 'system'),
  line('Type a command or click a quick-action. Use BOOT EVA to start all services.', 'system'),
  line('─────────────────────────────────────────────', 'system'),
];

export function TerminalPanel() {
  const [lines, setLines]               = useState<OutputLine[]>(STARTUP);
  const [input, setInput]               = useState('');
  const [isRunning, setIsRunning]       = useState(false);
  const [launcherOnline, setLauncherOnline] = useState(false);
  const [history, setHistory]           = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const [booting, setBooting]           = useState(false);
  const [bootSteps, setBootSteps]       = useState<BootStep[]>([]);
  const [showBoot, setShowBoot]         = useState(false);

  const outputRef = useRef<HTMLDivElement>(null);
  const inputRef  = useRef<HTMLInputElement>(null);

  // Auto-scroll
  useEffect(() => {
    const el = outputRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines]);

  // Ping launcher on mount + every 15s
  useEffect(() => {
    const ping = async () => {
      try {
        const r = await fetch(`${LAUNCHER}/health`, { signal: AbortSignal.timeout(2000) });
        setLauncherOnline(r.ok);
      } catch { setLauncherOnline(false); }
    };
    ping();
    const id = setInterval(ping, 15000);
    return () => clearInterval(id);
  }, []);

  const append = useCallback((newLines: OutputLine[]) => {
    setLines(prev => [...prev, ...newLines]);
  }, []);

  // Core exec — returns result or null on network error
  const exec = useCallback(async (command: string, silent = false): Promise<ExecResult | null> => {
    try {
      const r = await fetch(`${LAUNCHER}/terminal/exec`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command, timeout: 60 }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const result: ExecResult = await r.json();
      setLauncherOnline(true);
      if (!silent) {
        const out: OutputLine[] = [];
        if (result.stdout) result.stdout.split('\n').filter(Boolean).forEach(l => out.push(line(l, 'output')));
        if (result.stderr) result.stderr.split('\n').filter(Boolean).forEach(l => out.push(line(l, 'error')));
        const badge = result.exit_code === 0
          ? `✓ done (${result.duration_ms}ms)`
          : `✗ exited ${result.exit_code} (${result.duration_ms}ms)`;
        out.push(line(badge, result.exit_code === 0 ? 'system' : 'error'));
        append(out);
      }
      return result;
    } catch {
      setLauncherOnline(false);
      if (!silent) append([line('⚠ Launcher offline — start EVA Launcher on your Mac first', 'error')]);
      return null;
    }
  }, [append]);

  // Run a single command from input/chip
  const runCommand = useCallback(async (command: string) => {
    if (!command.trim() || isRunning || booting) return;
    const trimmed = command.trim();
    append([line(`$ ${trimmed}`, 'command')]);
    setHistory(prev => [trimmed, ...prev.filter(h => h !== trimmed)].slice(0, MAX_HISTORY));
    setHistoryIndex(-1);
    setInput('');
    setIsRunning(true);
    await exec(trimmed);
    setIsRunning(false);
    inputRef.current?.focus();
  }, [isRunning, booting, append, exec]);

  // Boot sequence — runs steps in order, updates status panel live
  const runBoot = useCallback(async () => {
    if (booting || isRunning) return;
    setBooting(true);
    setShowBoot(true);
    const steps: BootStep[] = BOOT_SEQUENCE.map(s => ({ ...s, status: 'pending' }));
    setBootSteps([...steps]);
    append([line('', 'system'), line('━━━━━ BOOT EVA — starting sequence ━━━━━', 'system')]);

    for (let i = 0; i < steps.length; i++) {
      // Mark current step running
      steps[i].status = 'running';
      setBootSteps([...steps]);
      append([line(`[${i + 1}/${steps.length}] ${steps[i].label}…`, 'command')]);

      const result = await exec(steps[i].command);

      if (result === null) {
        // Launcher went offline
        steps[i].status = 'fail';
        for (let j = i + 1; j < steps.length; j++) steps[j].status = 'skipped';
        setBootSteps([...steps]);
        append([line('Boot sequence aborted — Launcher went offline.', 'error')]);
        break;
      }

      // For port checks, parse OPEN/CLOSED
      if (steps[i].label.startsWith('port check')) {
        const combined = (result.stdout + result.stderr).toLowerCase();
        steps[i].status = combined.includes('open') ? 'ok' : 'fail';
      } else {
        steps[i].status = result.exit_code === 0 ? 'ok' : 'fail';
      }
      setBootSteps([...steps]);

      // Small gap between steps
      await new Promise(res => setTimeout(res, 300));
    }

    const allOk = steps.every(s => s.status === 'ok');
    append([
      line('', 'system'),
      line(allOk ? '✓ Boot complete — all services online' : '⚠ Boot done — some services need attention (check logs)', allOk ? 'system' : 'error'),
      line('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━', 'system'),
    ]);
    setBooting(false);
    inputRef.current?.focus();
  }, [booting, isRunning, append, exec]);

  const handleKeyDown = useCallback((e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter')     { runCommand(input); return; }
    if (e.key === 'ArrowUp')   { e.preventDefault(); setHistoryIndex(prev => { const n = Math.min(prev + 1, history.length - 1); if (history[n]) setInput(history[n]); return n; }); }
    if (e.key === 'ArrowDown') { e.preventDefault(); setHistoryIndex(prev => { const n = prev - 1; if (n < 0) { setInput(''); return -1; } if (history[n]) setInput(history[n]); return n; }); }
  }, [input, history, runCommand]);

  const stepIcon = (s: BootStep['status']) => {
    if (s === 'pending')  return <span className="text-gray-600">○</span>;
    if (s === 'running')  return <span className="text-yellow-400 animate-pulse">◎</span>;
    if (s === 'ok')       return <span className="text-green-400">✓</span>;
    if (s === 'fail')     return <span className="text-red-400">✗</span>;
    if (s === 'skipped')  return <span className="text-gray-600">–</span>;
  };

  const lineClass = (type: OutputLine['type']) => {
    if (type === 'error')   return 'text-red-400';
    if (type === 'system')  return 'text-cyan-400';
    if (type === 'command') return 'text-green-300 font-semibold';
    return 'text-green-400';
  };

  const busy = isRunning || booting;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">

      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs tracking-widest text-gray-400 uppercase">Terminal</span>
          <span
            className={`w-2 h-2 rounded-full inline-block ${launcherOnline ? 'bg-green-400' : 'bg-gray-600'}`}
            title={launcherOnline ? 'Launcher :8768 online' : 'Launcher offline'}
          />
          {!launcherOnline && (
            <span className="font-mono text-xs text-yellow-500">launcher offline</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* BOOT EVA button */}
          <button
            onClick={runBoot}
            disabled={busy}
            className="text-xs font-mono px-3 py-1 rounded bg-green-900/40 border border-green-700/50 text-green-400 hover:bg-green-800/50 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer transition-colors font-semibold"
          >
            {booting ? '⟳ BOOTING…' : '⚡ BOOT EVA'}
          </button>
          <button
            onClick={() => setLines([line('─────────────────────────────────────────────', 'system')])}
            className="text-xs font-mono px-2 py-1 rounded bg-gray-800 border border-gray-700 text-gray-400 hover:bg-gray-700 cursor-pointer transition-colors"
          >
            CLEAR
          </button>
        </div>
      </div>

      {/* Boot status panel */}
      {showBoot && bootSteps.length > 0 && (
        <div className="mb-3 bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 flex flex-wrap gap-x-4 gap-y-1">
          {bootSteps.map((s, i) => (
            <div key={i} className="flex items-center gap-1.5 font-mono text-xs">
              {stepIcon(s.status)}
              <span className={
                s.status === 'ok'      ? 'text-green-400' :
                s.status === 'fail'    ? 'text-red-400' :
                s.status === 'running' ? 'text-yellow-400' :
                'text-gray-500'
              }>{s.label}</span>
            </div>
          ))}
        </div>
      )}

      {/* Quick chips */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        {QUICK_COMMANDS.map(qc => (
          <button
            key={qc.label}
            onClick={() => runCommand(qc.command)}
            disabled={busy}
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
        style={{ minHeight: 300, maxHeight: 500 }}
      >
        <div className="p-3 space-y-0.5">
          {lines.map(l => (
            <div key={l.id} className="flex gap-2 leading-5">
              <span className="text-gray-500 font-mono text-sm select-none shrink-0">[{l.timestamp}]</span>
              <span className={`font-mono text-sm break-all ${lineClass(l.type)}`}>{l.text}</span>
            </div>
          ))}
          {busy && (
            <div className="flex gap-2 leading-5">
              <span className="text-gray-500 font-mono text-sm select-none shrink-0">[{ts()}]</span>
              <span className="font-mono text-sm text-green-400 animate-pulse">running…</span>
            </div>
          )}
        </div>
      </div>

      {/* Input */}
      <div className="flex gap-2 items-center">
        <span className="font-mono text-sm text-green-400 shrink-0">$</span>
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={e => { setInput(e.target.value); setHistoryIndex(-1); }}
          onKeyDown={handleKeyDown}
          disabled={busy}
          placeholder="run command on your Mac..."
          className="flex-1 bg-gray-900 border border-gray-700 text-green-400 font-mono text-sm rounded px-3 py-1.5 placeholder-gray-600 focus:outline-none focus:border-cyan-700 disabled:opacity-50 transition-colors"
          autoComplete="off"
          spellCheck={false}
        />
        <button
          onClick={() => runCommand(input)}
          disabled={busy || !input.trim()}
          className="px-3 py-1.5 rounded bg-cyan-700 border border-cyan-600 text-white font-mono text-sm hover:bg-cyan-600 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer transition-colors"
        >→</button>
      </div>
    </div>
  );
}
