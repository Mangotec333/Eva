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
  { label: 'port check :8768',  command: 'nc -z localhost 8768 && echo "OPEN" || echo "CLOSED"' },
];

const QUICK_COMMANDS = [
  { label: 'git pull',          command: 'cd ~/Eva && git pull origin main' },
  { label: 'services status',   command: 'launchctl list | grep eva' },
  { label: 'install services',  command: 'bash ~/Eva/modules/autostart/eva-install-services.sh' },
  { label: 'content engine',    command: 'cd ~/Eva/modules/content-engine && python3 main.py' },
  { label: 'deal scout',        command: 'cd ~/Eva/modules/deal-scout && python3 main.py' },
  { label: 'logs: content',     command: 'tail -30 ~/Eva/logs/eva-content-engine.error.log' },
  { label: 'logs: deal scout',  command: 'tail -30 ~/Eva/logs/eva-deal-scout.error.log' },
  { label: 'linkedin status',   command: 'cd ~/Eva/modules/linkedin && python3 post.py --status' },
];

// LinkedIn OAuth workflow steps
const LINKEDIN_OAUTH_STEPS = [
  { label: 'git pull latest',   command: 'cd ~/Eva && git pull origin main' },
  { label: 'install deps',      command: 'cd ~/Eva/modules/linkedin && pip3 install -r requirements.txt -q' },
  { label: 'start OAuth server',command: 'pkill -f "oauth_handler" 2>/dev/null; cd ~/Eva/modules/linkedin && LINKEDIN_CLIENT_ID="${LINKEDIN_CLIENT_ID}" LINKEDIN_CLIENT_SECRET="${LINKEDIN_CLIENT_SECRET}" uvicorn oauth_handler:app --host 0.0.0.0 --port 8773 &' },
  { label: 'wait for server',   command: 'sleep 2 && nc -z localhost 8773 && echo "SERVER_READY" || echo "SERVER_NOT_READY"' },
  { label: 'check token saved', command: 'python3 -c "import json,os; d=json.load(open(os.path.expanduser(\"~/.eva/channels_config.json\"))); li=d.get(\"linkedin\",{}); print(\"CONNECTED: \"+li[\"person_urn\"] if li.get(\"access_token\") and li.get(\"person_urn\") else \"NOT_CONNECTED\")"' },
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

type WorkflowStep = {
  label: string;
  command: string;
  status: 'pending' | 'running' | 'ok' | 'fail' | 'skipped';
  note?: string;
};

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
  const [linkedinFlow, setLinkedinFlow] = useState(false);
  const [linkedinSteps, setLinkedinSteps] = useState<WorkflowStep[]>([]);
  const [linkedinConnected, setLinkedinConnected] = useState(false);
  const [showAuthPrompt, setShowAuthPrompt] = useState(false);
  const [linkedinClientId, setLinkedinClientId] = useState('');
  const [linkedinClientSecret, setLinkedinClientSecret] = useState('');
  const [showCredForm, setShowCredForm] = useState(false);

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

  // LinkedIn OAuth guided flow
  const runLinkedinOAuth = useCallback(async () => {
    if (booting || isRunning || linkedinFlow) return;
    if (!linkedinClientId || !linkedinClientSecret) {
      setShowCredForm(true);
      return;
    }
    setShowCredForm(false);
    setLinkedinFlow(true);
    setShowAuthPrompt(false);
    const steps: WorkflowStep[] = LINKEDIN_OAUTH_STEPS.map(s => ({ ...s, status: 'pending' }));
    setLinkedinSteps([...steps]);
    append([line('', 'system'), line('━━━━━ LINKEDIN OAUTH — starting flow ━━━━━', 'system')]);

    for (let i = 0; i < steps.length; i++) {
      steps[i].status = 'running';
      setLinkedinSteps([...steps]);
      append([line(`[${i + 1}/${steps.length}] ${steps[i].label}…`, 'command')]);

      // Inject creds into OAuth server start command
      let cmd = steps[i].command
        .replace('${LINKEDIN_CLIENT_ID}', linkedinClientId)
        .replace('${LINKEDIN_CLIENT_SECRET}', linkedinClientSecret);

      const result = await exec(cmd);
      if (result === null) {
        steps[i].status = 'fail';
        for (let j = i + 1; j < steps.length; j++) steps[j].status = 'skipped';
        setLinkedinSteps([...steps]);
        break;
      }

      // Step 3: server started — prompt user to open browser
      if (i === 2) {
        steps[i].status = result.exit_code === 0 ? 'ok' : 'fail';
        setLinkedinSteps([...steps]);
        if (result.exit_code === 0) {
          setShowAuthPrompt(true);
          append([line('✓ OAuth server running on :8773', 'system')]);
          append([line('👉 Open http://localhost:8773/linkedin/login in your browser to authorize', 'system')]);
          append([line('Waiting for you to complete authorization…', 'system')]);
          // Poll for token every 5 seconds, up to 3 minutes
          let authorized = false;
          for (let poll = 0; poll < 36; poll++) {
            await new Promise(res => setTimeout(res, 5000));
            const checkResult = await exec(LINKEDIN_OAUTH_STEPS[4].command, true);
            if (checkResult?.stdout?.includes('CONNECTED')) {
              authorized = true;
              break;
            }
          }
          if (authorized) {
            setShowAuthPrompt(false);
            setLinkedinConnected(true);
            append([line('✅ LinkedIn connected! Token saved to ~/.eva/channels_config.json', 'system')]);
            append([line('Auto-posting is now live. EVA will post on your behalf.', 'system')]);
            // Kill OAuth server — no longer needed
            await exec('pkill -f "oauth_handler" 2>/dev/null; echo done', true);
          } else {
            append([line('⚠ Authorization timeout — retry the LinkedIn OAuth flow', 'error')]);
          }
          setLinkedinFlow(false);
          return;
        }
        continue;
      }

      // Step 4 (wait for server): check SERVER_READY
      if (i === 3) {
        const combined = (result.stdout + result.stderr);
        steps[i].status = combined.includes('SERVER_READY') ? 'ok' : 'fail';
      } else {
        steps[i].status = result.exit_code === 0 ? 'ok' : 'fail';
      }
      setLinkedinSteps([...steps]);
      await new Promise(res => setTimeout(res, 300));
    }

    setLinkedinFlow(false);
  }, [booting, isRunning, linkedinFlow, linkedinClientId, linkedinClientSecret, append, exec]);

  const handleKeyDown = useCallback((e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter')     { runCommand(input); return; }
    if (e.key === 'ArrowUp')   { e.preventDefault(); setHistoryIndex(prev => { const n = Math.min(prev + 1, history.length - 1); if (history[n]) setInput(history[n]); return n; }); }
    if (e.key === 'ArrowDown') { e.preventDefault(); setHistoryIndex(prev => { const n = prev - 1; if (n < 0) { setInput(''); return -1; } if (history[n]) setInput(history[n]); return n; }); }
  }, [input, history, runCommand]);

  const stepIcon = (s: BootStep['status']) => {
    if (s === 'pending')  return <span className="text-gray-500">○</span>;
    if (s === 'running')  return <span className="text-yellow-400 animate-pulse">◎</span>;
    if (s === 'ok')       return <span className="text-green-400">✓</span>;
    if (s === 'fail')     return <span className="text-red-400">✗</span>;
    if (s === 'skipped')  return <span className="text-gray-500">–</span>;
  };

  const lineClass = (type: OutputLine['type']) => {
    if (type === 'error')   return 'text-red-400';
    if (type === 'system')  return 'text-cyan-400';
    if (type === 'command') return 'text-green-300 font-semibold';
    return 'text-green-400';
  };

  const busy = isRunning || booting;

  return (
    <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">

      {/* Header */}
      <div className="flex items-center justify-between mb-3">

        <div className="flex items-center gap-2">
          <span className="font-mono text-xs tracking-widest text-gray-500 uppercase">Terminal</span>
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
            className="text-xs font-mono px-2 py-1 rounded bg-gray-100 border border-gray-200 text-gray-500 hover:bg-gray-200 cursor-pointer transition-colors"
          >
            CLEAR
          </button>
        </div>
      </div>

      {/* Boot status panel */}
      {showBoot && bootSteps.length > 0 && (
        <div className="mb-3 bg-white border border-gray-200 rounded-lg px-3 py-2 flex flex-wrap gap-x-4 gap-y-1">
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

      {/* LinkedIn OAuth Workflow Panel */}
      {(linkedinFlow || showCredForm || linkedinConnected) && (
        <div className="mb-3 bg-white border border-gray-200 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-2">
            <span className="font-mono text-xs font-semibold text-cyan-400 tracking-wider">LINKEDIN OAUTH</span>
            {linkedinConnected && <span className="text-xs font-mono text-green-400">✅ CONNECTED</span>}
          </div>

          {/* Cred form */}
          {showCredForm && (
            <div className="space-y-2 mb-2">
              <p className="font-mono text-xs text-gray-500">Enter your LinkedIn App credentials to begin:</p>
              <input
                type="text"
                placeholder="Client ID"
                value={linkedinClientId}
                onChange={e => setLinkedinClientId(e.target.value)}
                className="w-full bg-gray-50 border border-gray-200 text-green-400 font-mono text-xs rounded px-2 py-1 focus:outline-none focus:border-cyan-700"
              />
              <input
                type="password"
                placeholder="Client Secret"
                value={linkedinClientSecret}
                onChange={e => setLinkedinClientSecret(e.target.value)}
                className="w-full bg-gray-50 border border-gray-200 text-green-400 font-mono text-xs rounded px-2 py-1 focus:outline-none focus:border-cyan-700"
              />
              <button
                onClick={runLinkedinOAuth}
                disabled={!linkedinClientId || !linkedinClientSecret}
                className="text-xs font-mono px-3 py-1 rounded bg-cyan-900/40 border border-cyan-700/50 text-cyan-400 hover:bg-cyan-800/50 disabled:opacity-50 cursor-pointer transition-colors"
              >
                Start OAuth Flow →
              </button>
              <p className="font-mono text-xs text-gray-500 mt-1">
                Get credentials at{' '}
                <a href="https://www.linkedin.com/developers/apps" target="_blank" rel="noreferrer" className="text-cyan-400 underline">linkedin.com/developers/apps</a>
                {' '}→ Auth tab. Add redirect URL: <code className="text-green-400">http://localhost:8773/linkedin/callback</code>
              </p>
            </div>
          )}

          {/* Step progress */}
          {linkedinSteps.length > 0 && (
            <div className="flex flex-wrap gap-x-4 gap-y-1 mb-2">
              {linkedinSteps.map((s, i) => (
                <div key={i} className="flex items-center gap-1.5 font-mono text-xs">
                  {s.status === 'pending'  && <span className="text-gray-500">○</span>}
                  {s.status === 'running'  && <span className="text-yellow-400 animate-pulse">◎</span>}
                  {s.status === 'ok'       && <span className="text-green-400">✓</span>}
                  {s.status === 'fail'     && <span className="text-red-400">✗</span>}
                  {s.status === 'skipped'  && <span className="text-gray-500">–</span>}
                  <span className={s.status === 'ok' ? 'text-green-400' : s.status === 'fail' ? 'text-red-400' : s.status === 'running' ? 'text-yellow-400' : 'text-gray-500'}>
                    {s.label}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Auth prompt */}
          {showAuthPrompt && (
            <div className="bg-yellow-900/20 border border-yellow-700/40 rounded px-3 py-2">
              <p className="font-mono text-xs text-yellow-400 font-semibold mb-1">👉 Action required</p>
              <p className="font-mono text-xs text-yellow-300">Open this URL in your browser to authorize EVA:</p>
              <a
                href="http://localhost:8773/linkedin/login"
                target="_blank"
                rel="noreferrer"
                className="font-mono text-xs text-cyan-400 underline block mt-1"
              >
                http://localhost:8773/linkedin/login
              </a>
              <p className="font-mono text-xs text-gray-500 mt-1">Waiting for authorization… (polls every 5s, 3 min timeout)</p>
            </div>
          )}
        </div>
      )}

      {/* Quick chips */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        {/* LinkedIn OAuth button */}
        <button
          onClick={() => {
            if (linkedinConnected) {
              append([line('LinkedIn already connected. Run "linkedin status" to verify.', 'system')]);
              return;
            }
            setShowCredForm(true);
            setLinkedinSteps([]);
          }}
          disabled={busy || linkedinFlow}
          className={`text-xs font-mono px-2 py-1 rounded border cursor-pointer transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
            linkedinConnected
              ? 'bg-green-900/30 border-green-700/50 text-green-400'
              : 'bg-blue-900/30 border-blue-700/50 text-blue-300 hover:bg-blue-800/30'
          }`}
        >
          {linkedinConnected ? '✅ linkedin' : '🔗 linkedin oauth'}
        </button>
        {QUICK_COMMANDS.map(qc => (
          <button
            key={qc.label}
            onClick={() => runCommand(qc.command)}
            disabled={busy}
            className="text-xs font-mono px-2 py-1 rounded bg-gray-100 border border-gray-200 text-cyan-400 hover:bg-gray-200 cursor-pointer transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {qc.label}
          </button>
        ))}
      </div>

      {/* Output area */}
      <div
        ref={outputRef}
        className="bg-white border border-gray-200 rounded-lg overflow-y-auto mb-3"
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
          className="flex-1 bg-gray-50 border border-gray-200 text-green-400 font-mono text-sm rounded px-3 py-1.5 placeholder-gray-600 focus:outline-none focus:border-cyan-700 disabled:opacity-50 transition-colors"
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
