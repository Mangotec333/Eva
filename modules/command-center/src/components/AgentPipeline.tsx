import { useState, useCallback, useEffect, useRef } from 'react';
import { ChevronDown, ChevronUp, Send, Play } from 'lucide-react';

// ─── Stage definitions ────────────────────────────────────────────────────────
const STAGES = [
  'GOAL',
  'PLAN',
  'STEPS',
  'TOOL CALLS',
  'APPROVALS',
  'RESULT',
  'NEXT ACTION',
] as const;

type Stage = (typeof STAGES)[number];

const STAGE_CONTENT: Record<Stage, React.ReactNode> = {
  GOAL: (
    <div className="flex flex-col gap-2">
      <div className="font-mono text-xs text-gray-500 tracking-widest uppercase mb-1">Active Goal</div>
      <div className="font-mono text-sm text-white font-semibold">
        Sign NDA on EF #87872 Digital Media Services
      </div>
      <div className="font-mono text-xs text-gray-500 mt-1">
        Source: Empire Flippers · Listing #87872 · Digital Media · $4,800 MRR
      </div>
    </div>
  ),
  PLAN: (
    <div className="flex flex-col gap-2">
      <div className="font-mono text-xs text-gray-500 tracking-widest uppercase mb-1">Execution Plan</div>
      <ol className="flex flex-col gap-1.5">
        {[
          'Navigate to EF listing #87872',
          'Locate NDA / LOI form',
          "Fill with Vineet's contact & entity info",
          'Submit for Vineet approval before final submission',
        ].map((step, i) => (
          <li key={i} className="flex items-start gap-2">
            <span className="font-mono text-[10px] text-cyan-500 mt-0.5 shrink-0">{i + 1}.</span>
            <span className="font-mono text-xs text-gray-300">{step}</span>
          </li>
        ))}
      </ol>
    </div>
  ),
  STEPS: (
    <div className="flex flex-col gap-2">
      <div className="font-mono text-xs text-gray-500 tracking-widest uppercase mb-1">Progress</div>
      <div className="flex items-center gap-2 mb-2">
        <div className="flex-1 bg-gray-800 rounded-full h-1.5">
          <div className="bg-cyan-500 h-1.5 rounded-full" style={{ width: '25%' }} />
        </div>
        <span className="font-mono text-xs text-gray-400 shrink-0">1 / 4</span>
      </div>
      <div className="font-mono text-sm text-cyan-300 font-semibold">
        Step 1/4 — Opening Empire Flippers…
      </div>
      <div className="font-mono text-xs text-gray-500">
        browser_task: fetching empireflippers.com/listing/87872
      </div>
    </div>
  ),
  'TOOL CALLS': (
    <div className="flex flex-col gap-2">
      <div className="font-mono text-xs text-gray-500 tracking-widest uppercase mb-1">Active Tool Call</div>
      <code className="font-mono text-xs text-green-400 bg-gray-950 border border-gray-800 rounded px-3 py-2 block leading-relaxed">
        browser_task(<br />
        &nbsp;&nbsp;url='empireflippers.com/listing/87872',<br />
        &nbsp;&nbsp;action='navigate_and_extract',<br />
        &nbsp;&nbsp;target='nda_form_url'<br />
        )
      </code>
      <div className="font-mono text-[10px] text-gray-600">
        tool: browser · timeout: 30s · status: running
      </div>
    </div>
  ),
  APPROVALS: (
    <div className="flex flex-col gap-3">
      <div className="font-mono text-xs text-gray-500 tracking-widest uppercase mb-1">Approval Required</div>
      <div className="bg-amber-500/10 border border-amber-500/40 rounded-lg px-4 py-3">
        <div className="flex items-start gap-2">
          <span className="text-amber-400 text-base shrink-0">⚠</span>
          <div className="font-mono text-sm text-amber-300 font-semibold">
            EVA wants to submit NDA form on your behalf. Approve?
          </div>
        </div>
        <div className="font-mono text-xs text-gray-500 mt-2">
          Form: Empire Flippers NDA · Listing #87872 · Digital Media Services
        </div>
      </div>
      <div className="flex gap-2">
        <button className="flex-1 px-4 py-2 bg-green-500/20 border border-green-500/50 text-green-400 rounded font-mono text-xs font-bold hover:bg-green-500/30 transition-colors active:scale-95">
          ✓ APPROVE
        </button>
        <button className="flex-1 px-4 py-2 bg-red-500/10 border border-red-500/30 text-red-400 rounded font-mono text-xs font-bold hover:bg-red-500/20 transition-colors active:scale-95">
          ✗ DENY
        </button>
      </div>
    </div>
  ),
  RESULT: (
    <div className="flex flex-col gap-2">
      <div className="font-mono text-xs text-gray-500 tracking-widest uppercase mb-1">Result</div>
      <div className="flex items-center gap-2">
        <span className="text-green-400 text-base">✓</span>
        <div className="font-mono text-sm text-green-400 font-semibold">
          NDA submitted successfully.
        </div>
      </div>
      <div className="font-mono text-xs text-gray-400 bg-gray-950 border border-gray-800 rounded px-3 py-2">
        Confirmation #EF-2847 · Empire Flippers · Digital Media Services #87872<br />
        Submitted: {new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })} · Status: Pending broker review
      </div>
    </div>
  ),
  'NEXT ACTION': (
    <div className="flex flex-col gap-2">
      <div className="font-mono text-xs text-gray-500 tracking-widest uppercase mb-1">Recommended Next</div>
      <div className="font-mono text-sm text-cyan-300 font-semibold">
        Schedule follow-up call with EF broker in 48 hours
      </div>
      <div className="font-mono text-xs text-gray-500">
        Broker typically responds within 1-2 business days after NDA review.
      </div>
    </div>
  ),
};

// ─── Radar animation ──────────────────────────────────────────────────────────
function RadarPulse() {
  return (
    <div className="flex flex-col items-center justify-center py-6 gap-4">
      <div className="radar-pulse" />
      <div className="font-mono text-xs text-gray-600 tracking-widest">EVA IDLE — awaiting task</div>
    </div>
  );
}

// ─── Stage Tabs ───────────────────────────────────────────────────────────────
function StageTabs({
  activeStage,
  completedStages,
  onSelect,
}: {
  activeStage: Stage | null;
  completedStages: Set<Stage>;
  onSelect: (s: Stage) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5 py-3 border-b border-gray-800">
      {STAGES.map(stage => {
        const isActive = stage === activeStage;
        const isDone = completedStages.has(stage);
        return (
          <button
            key={stage}
            onClick={() => onSelect(stage)}
            className={`
              flex items-center gap-1 px-2.5 py-1 rounded font-mono text-[10px] font-bold tracking-widest transition-all duration-150
              ${isActive
                ? 'bg-cyan-500/25 border border-cyan-400/70 text-cyan-300'
                : isDone
                ? 'bg-green-500/10 border border-green-500/30 text-green-400'
                : 'bg-gray-800 border border-gray-700 text-gray-500 hover:text-gray-300 hover:border-gray-600'}
            `}
          >
            {isDone && <span className="text-green-400">✓</span>}
            {stage}
          </button>
        );
      })}
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────
export function AgentPipeline() {
  const [collapsed, setCollapsed] = useState(true);
  const [activeStage, setActiveStage] = useState<Stage | null>(null);
  const [completedStages, setCompletedStages] = useState<Set<Stage>>(new Set());
  const [demoRunning, setDemoRunning] = useState(false);
  const [taskInput, setTaskInput] = useState('');
  const demoRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Demo mode: cycle through stages
  const handleDemo = useCallback(() => {
    if (demoRunning) return;
    setDemoRunning(true);
    setCollapsed(false);
    setActiveStage(null);
    setCompletedStages(new Set());

    let idx = 0;
    const runNext = () => {
      if (idx >= STAGES.length) {
        setDemoRunning(false);
        return;
      }
      const stage = STAGES[idx];
      setActiveStage(stage);
      if (idx > 0) {
        setCompletedStages(prev => {
          const next = new Set(prev);
          next.add(STAGES[idx - 1]);
          return next;
        });
      }
      idx++;
      demoRef.current = setTimeout(runNext, 2000);
    };
    runNext();
  }, [demoRunning]);

  useEffect(() => {
    return () => {
      if (demoRef.current) clearTimeout(demoRef.current);
    };
  }, []);

  const isIdle = activeStage === null;

  // Header stage pill
  const stagePill = activeStage ? (
    <span className="font-mono text-[10px] font-bold px-2 py-0.5 bg-cyan-500/20 border border-cyan-400/50 text-cyan-300 rounded tracking-widest">
      {activeStage}
    </span>
  ) : (
    <span className="font-mono text-[10px] font-bold px-2 py-0.5 bg-gray-800 border border-gray-700 text-gray-500 rounded tracking-widest">
      IDLE
    </span>
  );

  return (
    <div className="bg-gray-900/60 border border-gray-800 rounded-xl overflow-hidden">
      {/* Header — always visible, click to toggle */}
      <button
        className="w-full flex items-center justify-between px-4 py-3 border-b border-gray-800 bg-gray-900 hover:bg-gray-800/50 transition-colors"
        onClick={() => setCollapsed(c => !c)}
      >
        <div className="flex items-center gap-3">
          {/* Radar dot */}
          <div className={`w-2 h-2 rounded-full shrink-0 ${demoRunning ? 'bg-cyan-400 animate-pulse' : isIdle ? 'bg-gray-700' : 'bg-cyan-400 animate-pulse'}`} />
          <div className="text-left">
            <div className="font-mono text-xs font-bold text-gray-100 tracking-widest uppercase">
              EVA ACTIVE TASK
            </div>
            <div className="font-mono text-[10px] text-gray-500 tracking-wide mt-0.5">
              Agent execution pipeline
            </div>
          </div>
          <div className="ml-2">{stagePill}</div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {/* Demo button */}
          <button
            onClick={e => { e.stopPropagation(); handleDemo(); }}
            disabled={demoRunning}
            className="flex items-center gap-1 px-2.5 py-1 bg-gray-800 border border-gray-700 text-gray-400 rounded font-mono text-[10px] font-bold hover:text-gray-200 hover:border-gray-500 transition-colors disabled:opacity-50"
          >
            <Play className="w-2.5 h-2.5" />
            DEMO
          </button>
          {collapsed ? (
            <ChevronDown className="w-4 h-4 text-gray-600" />
          ) : (
            <ChevronUp className="w-4 h-4 text-gray-600" />
          )}
        </div>
      </button>

      {/* Collapsible body */}
      {!collapsed && (
        <div className="px-4 pb-4">
          {/* Stage Tabs */}
          {!isIdle && (
            <StageTabs
              activeStage={activeStage}
              completedStages={completedStages}
              onSelect={setActiveStage}
            />
          )}

          {/* Content area */}
          <div className="pt-4">
            {isIdle ? (
              <>
                <RadarPulse />
                {/* Task input */}
                <div className="flex gap-2 mt-2">
                  <input
                    type="text"
                    value={taskInput}
                    onChange={e => setTaskInput(e.target.value)}
                    placeholder="Give EVA a task..."
                    className="flex-1 bg-gray-950 border border-gray-700 rounded px-3 py-2 font-mono text-xs text-gray-200 placeholder:text-gray-700 focus:outline-none focus:border-cyan-500/60 transition-colors"
                  />
                  <button
                    className="flex items-center gap-1.5 px-3 py-2 bg-cyan-500/20 border border-cyan-400/50 text-cyan-300 rounded font-mono text-xs font-bold hover:bg-cyan-500/30 hover:border-cyan-400/80 transition-colors active:scale-95"
                  >
                    <Send className="w-3 h-3" />
                    SEND
                  </button>
                </div>
              </>
            ) : (
              <div className="min-h-[120px]">
                {activeStage && STAGE_CONTENT[activeStage]}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
