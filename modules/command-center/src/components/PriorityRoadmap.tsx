import { useState } from 'react';
import { CheckSquare, Clock, Zap, AlertCircle, Circle, ChevronRight } from 'lucide-react';

interface Task {
  id: number;
  priority: number;
  title: string;
  description: string;
  tag: 'BUILD' | 'REVENUE' | 'DEPLOY' | 'DEADLINE' | 'INFRA';
  status: 'blocked' | 'ready' | 'in_progress' | 'done';
  blockers?: string;
  etaHours: number; // estimated hours to complete
  progressPct: number; // 0-100
  urgency: 'critical' | 'high' | 'medium';
}

const TASKS: Task[] = [
  {
    id: 1,
    priority: 1,
    title: 'Email Agent + Morning Brief',
    description: 'Scan Gmail + Calendar daily 7am — extract deal URLs, update DB, generate brief in UI',
    tag: 'BUILD',
    status: 'in_progress',
    blockers: undefined,
    etaHours: 3,
    progressPct: 40,
    urgency: 'high',
  },
  {
    id: 2,
    priority: 2,
    title: 'Shopify Store Live',
    description: 'Fix EVA3 app token → Picker agent → Margin Guard → Courier → Pureplate running itself',
    tag: 'BUILD',
    status: 'blocked',
    blockers: 'Need shpat_ token: change EVA3 App URL to eva.mangotec.ai, uninstall → reinstall',
    etaHours: 4,
    progressPct: 25,
    urgency: 'high',
  },
  {
    id: 3,
    priority: 3,
    title: 'Online Biz Scout',
    description: 'Forensic scoring of Empire Flippers + Flippa listings — find the right $150–350K acquisition',
    tag: 'REVENUE',
    status: 'ready',
    blockers: undefined,
    etaHours: 2,
    progressPct: 0,
    urgency: 'high',
  },
  {
    id: 4,
    priority: 4,
    title: 'DealScout — 10 LinkedIn DMs',
    description: 'Send 10 personalized DMs to ETA searchers · $49/mo pitch · first cash this week',
    tag: 'REVENUE',
    status: 'ready',
    blockers: undefined,
    etaHours: 1,
    progressPct: 0,
    urgency: 'critical',
  },
  {
    id: 5,
    priority: 5,
    title: 'Signature Talk — The Hail Mary',
    description: 'Story extraction + full draft · "Logic maps the road. Intuition feels the turn. Faith takes the step."',
    tag: 'DEADLINE',
    status: 'in_progress',
    blockers: undefined,
    etaHours: 6,
    progressPct: 30,
    urgency: 'critical',
  },
  {
    id: 6,
    priority: 6,
    title: 'Light Mode UI Deploy',
    description: 'New Netlify token → deploy white theme to eva.mangotec.ai',
    tag: 'DEPLOY',
    status: 'blocked',
    blockers: 'Need new Netlify token: app.netlify.com → User Settings → Access tokens → new token',
    etaHours: 0.5,
    progressPct: 80,
    urgency: 'medium',
  },
  {
    id: 7,
    priority: 7,
    title: 'Mac Bootstrap — Sentinel Live',
    description: 'Run once: cd ~/Eva && git pull origin main && bash modules/angels/angel0_sentinel/bootstrap.sh',
    tag: 'INFRA',
    status: 'blocked',
    blockers: 'Blocked on you — run bootstrap command on Mac terminal',
    etaHours: 0.25,
    progressPct: 90,
    urgency: 'medium',
  },
];

const TAG_STYLES: Record<Task['tag'], { bg: string; text: string; border: string }> = {
  BUILD:    { bg: 'bg-cyan-50',   text: 'text-cyan-700',   border: 'border-cyan-200' },
  REVENUE:  { bg: 'bg-green-50',  text: 'text-green-700',  border: 'border-green-200' },
  DEPLOY:   { bg: 'bg-violet-50', text: 'text-violet-700', border: 'border-violet-200' },
  DEADLINE: { bg: 'bg-rose-50',   text: 'text-rose-700',   border: 'border-rose-200' },
  INFRA:    { bg: 'bg-amber-50',  text: 'text-amber-700',  border: 'border-amber-200' },
};

const STATUS_STYLES: Record<Task['status'], { icon: JSX.Element; label: string; color: string }> = {
  ready:      { icon: <Circle className="w-3 h-3" />,      label: 'READY',      color: 'text-cyan-500' },
  in_progress:{ icon: <Zap className="w-3 h-3" />,         label: 'IN PROGRESS',color: 'text-amber-500' },
  blocked:    { icon: <AlertCircle className="w-3 h-3" />, label: 'BLOCKED',    color: 'text-rose-500' },
  done:       { icon: <CheckSquare className="w-3 h-3" />, label: 'DONE',       color: 'text-green-500' },
};

const URGENCY_BAR: Record<Task['urgency'], string> = {
  critical: 'bg-rose-500',
  high:     'bg-amber-400',
  medium:   'bg-cyan-400',
};

function etaLabel(hours: number): string {
  if (hours < 1) return `${Math.round(hours * 60)}min`;
  if (hours === 1) return '1hr';
  return `${hours}hrs`;
}

function TaskRow({ task, rank }: { task: Task; rank: number }) {
  const [expanded, setExpanded] = useState(false);
  const tag = TAG_STYLES[task.tag];
  const status = STATUS_STYLES[task.status];

  return (
    <div
      className={`rounded-xl border transition-all duration-200 overflow-hidden
        ${task.status === 'blocked' ? 'border-rose-100 bg-rose-50/30' : 'border-gray-200 bg-white'}
        ${task.urgency === 'critical' ? 'ring-1 ring-rose-200' : ''}
      `}
    >
      {/* Main row */}
      <button
        className="w-full text-left px-4 py-3 flex items-center gap-3"
        onClick={() => setExpanded(!expanded)}
      >
        {/* Rank badge */}
        <div className={`
          flex-shrink-0 w-7 h-7 rounded-lg flex items-center justify-center font-mono text-xs font-bold
          ${rank <= 2 ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-600'}
        `}>
          {rank}
        </div>

        {/* Title + tag */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-gray-900 truncate">{task.title}</span>
            <span className={`px-1.5 py-0.5 rounded border text-[10px] font-bold font-mono ${tag.bg} ${tag.text} ${tag.border}`}>
              {task.tag}
            </span>
            {task.urgency === 'critical' && (
              <span className="px-1.5 py-0.5 rounded border text-[10px] font-bold font-mono bg-rose-50 text-rose-600 border-rose-200">
                ⚡ CRITICAL
              </span>
            )}
          </div>

          {/* Progress bar */}
          <div className="mt-2 flex items-center gap-2">
            <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${URGENCY_BAR[task.urgency]}`}
                style={{ width: `${task.progressPct}%` }}
              />
            </div>
            <span className="font-mono text-[10px] text-gray-400 flex-shrink-0">{task.progressPct}%</span>
          </div>
        </div>

        {/* Status + ETA */}
        <div className="flex-shrink-0 flex flex-col items-end gap-1">
          <div className={`flex items-center gap-1 font-mono text-[10px] font-bold ${status.color}`}>
            {status.icon}
            {status.label}
          </div>
          <div className="flex items-center gap-1 text-gray-400 font-mono text-[10px]">
            <Clock className="w-3 h-3" />
            {etaLabel(task.etaHours)} left
          </div>
        </div>

        <ChevronRight className={`w-4 h-4 text-gray-300 flex-shrink-0 transition-transform duration-200 ${expanded ? 'rotate-90' : ''}`} />
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="px-4 pb-3 pt-0 border-t border-gray-100">
          <p className="text-sm text-gray-600 mt-2 leading-relaxed">{task.description}</p>
          {task.blockers && (
            <div className="mt-2 flex items-start gap-2 px-3 py-2 bg-rose-50 border border-rose-100 rounded-lg">
              <AlertCircle className="w-3.5 h-3.5 text-rose-500 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-rose-700 font-mono leading-relaxed">{task.blockers}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function PriorityRoadmap() {
  const totalHours = TASKS.filter(t => t.status !== 'done').reduce((s, t) => s + t.etaHours * (1 - t.progressPct / 100), 0);
  const done = TASKS.filter(t => t.status === 'done').length;
  const blocked = TASKS.filter(t => t.status === 'blocked').length;
  const critical = TASKS.filter(t => t.urgency === 'critical' && t.status !== 'done').length;

  return (
    <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-mono text-xs font-bold text-gray-900 tracking-widest uppercase">Priority Roadmap</h2>
          <p className="font-mono text-[10px] text-gray-400 mt-0.5">Ordered by impact · Click to expand</p>
        </div>
        <div className="flex items-center gap-3">
          {critical > 0 && (
            <div className="flex items-center gap-1 px-2 py-1 bg-rose-50 border border-rose-100 rounded-lg">
              <Zap className="w-3 h-3 text-rose-500" />
              <span className="font-mono text-[10px] text-rose-600 font-bold">{critical} CRITICAL</span>
            </div>
          )}
          {blocked > 0 && (
            <div className="flex items-center gap-1 px-2 py-1 bg-amber-50 border border-amber-100 rounded-lg">
              <AlertCircle className="w-3 h-3 text-amber-500" />
              <span className="font-mono text-[10px] text-amber-600 font-bold">{blocked} BLOCKED</span>
            </div>
          )}
          <div className="flex items-center gap-1 px-2 py-1 bg-gray-100 border border-gray-200 rounded-lg">
            <Clock className="w-3 h-3 text-gray-500" />
            <span className="font-mono text-[10px] text-gray-600 font-bold">~{Math.ceil(totalHours)}h total</span>
          </div>
        </div>
      </div>

      {/* Summary bar */}
      <div className="grid grid-cols-3 gap-2">
        {[
          { label: 'Done', value: done, color: 'text-green-600', bg: 'bg-green-50', border: 'border-green-100' },
          { label: 'In Progress', value: TASKS.filter(t => t.status === 'in_progress').length, color: 'text-amber-600', bg: 'bg-amber-50', border: 'border-amber-100' },
          { label: 'Blocked', value: blocked, color: 'text-rose-600', bg: 'bg-rose-50', border: 'border-rose-100' },
        ].map(s => (
          <div key={s.label} className={`${s.bg} border ${s.border} rounded-lg px-3 py-2 text-center`}>
            <div className={`font-mono text-lg font-bold ${s.color}`}>{s.value}</div>
            <div className={`font-mono text-[10px] ${s.color} opacity-70`}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* Task list */}
      <div className="flex flex-col gap-2">
        {TASKS.map((task, i) => (
          <TaskRow key={task.id} task={task} rank={i + 1} />
        ))}
      </div>

      {/* Velocity note */}
      <p className="font-mono text-[10px] text-gray-400 text-center">
        ◆ Velocity estimate based on current build pace · Blockers reduce velocity to 0
      </p>
    </div>
  );
}
