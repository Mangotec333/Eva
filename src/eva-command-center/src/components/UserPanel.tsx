/**
 * UserPanel — Client-facing white-label EVA interface
 * Clean, simple, no internal ops. Loads user_profile.json for branding.
 */

import { useState, useEffect } from 'react';

/* ─────────────────────────────────────────
   TYPES
───────────────────────────────────────── */
interface UserTask {
  id: string;
  title: string;
  priority: 'high' | 'medium' | 'low';
  status: 'todo' | 'in_progress' | 'done';
  due?: string;
}

interface UserGoal {
  id: string;
  title: string;
  target: number;
  current: number;
  unit: string;
  color: string;
}

interface UserInsight {
  id: string;
  title: string;
  body: string;
  type: 'deal' | 'alert' | 'tip' | 'update';
  time: string;
}

type UserTab = 'dashboard' | 'tasks' | 'goals' | 'insights' | 'profile';

/* ─────────────────────────────────────────
   MOCK DATA (replaced by API when services live)
───────────────────────────────────────── */
const MOCK_TASKS: UserTask[] = [
  { id: '1', title: 'Review morning brief', priority: 'high', status: 'done' },
  { id: '2', title: 'Send Flippa outreach message', priority: 'high', status: 'in_progress', due: 'Today' },
  { id: '3', title: 'Publish LinkedIn intro post', priority: 'high', status: 'todo', due: 'Today' },
  { id: '4', title: 'Email Gutha Kannan — AI consulting', priority: 'high', status: 'todo', due: 'Today' },
  { id: '5', title: 'Finalize Signature Talk deck', priority: 'medium', status: 'todo', due: 'Wed' },
  { id: '6', title: 'Set NEON_DATABASE_URL in Vercel', priority: 'medium', status: 'todo', due: 'Today' },
  { id: '7', title: 'Speaker Kit Masterclass', priority: 'medium', status: 'todo', due: 'Thu 11am' },
  { id: '8', title: 'GovCon call — Jay Prasad', priority: 'medium', status: 'todo', due: 'Thu 9am' },
];

const MOCK_GOALS: UserGoal[] = [
  { id: '1', title: 'Monthly Net Revenue', target: 10000, current: 0, unit: '$', color: '#00C07F' },
  { id: '2', title: 'EVA Waitlist Signups', target: 200, current: 0, unit: '', color: '#4d9fff' },
  { id: '3', title: 'Active Deals in Pipeline', target: 5, current: 3, unit: '', color: '#ff9500' },
  { id: '4', title: 'GLŌSSAI Founding Members', target: 50, current: 0, unit: '', color: '#ff3b30' },
];

const MOCK_INSIGHTS: UserInsight[] = [
  { id: '1', title: 'Deal Alert — Flippa #12197961', body: 'Wellness SaaS MI · $9,154 net/mo · Outreach drafted and ready to send.', type: 'deal', time: 'Now' },
  { id: '2', title: 'Video Intel — BW Brands (EF #88148)', body: 'Scored 7.4/10 · Strong supplier moat · 100% Amazon risk flagged.', type: 'deal', time: '2h ago' },
  { id: '3', title: 'Neon DB not connected', body: 'Waitlist leads are not saving. Add NEON_DATABASE_URL to Vercel env.', type: 'alert', time: 'Today' },
  { id: '4', title: 'EVA Services offline', body: '0/6 Mac services running. Run install script to activate deal scout + content engine.', type: 'alert', time: 'Today' },
  { id: '5', title: 'LinkedIn post ready', body: 'EVA intro copy is written. Voice DNA applied. Post it today to start waitlist signups.', type: 'tip', time: 'Today' },
];

/* ─────────────────────────────────────────
   HELPERS
───────────────────────────────────────── */
const PRIORITY_COLOR = { high: '#ff3b30', medium: '#ff9500', low: '#4d9fff' };
const STATUS_COLOR   = { todo: '#6e7681', in_progress: '#ff9500', done: '#00C07F' };
const STATUS_LABEL   = { todo: 'To Do', in_progress: 'In Progress', done: 'Done' };
const INSIGHT_COLOR  = { deal: '#00C07F', alert: '#ff3b30', tip: '#4d9fff', update: '#ff9500' };
const INSIGHT_ICON   = { deal: '🎯', alert: '⚠️', tip: '💡', update: '📡' };

function pct(current: number, target: number) {
  return Math.min(Math.round((current / target) * 100), 100);
}

/* ─────────────────────────────────────────
   TAB BAR
───────────────────────────────────────── */
const USER_TABS: { id: UserTab; label: string; icon: string }[] = [
  { id: 'dashboard', label: 'Dashboard', icon: '⚡' },
  { id: 'tasks',     label: 'Tasks',     icon: '✅' },
  { id: 'goals',     label: 'Goals',     icon: '🎯' },
  { id: 'insights',  label: 'Insights',  icon: '🧠' },
  { id: 'profile',   label: 'Profile',   icon: '👤' },
];

/* ─────────────────────────────────────────
   DASHBOARD TAB
───────────────────────────────────────── */
function DashboardTab() {
  const now = new Date();
  const hour = now.getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
  const today = now.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });

  const todayTasks = MOCK_TASKS.filter(t => t.due === 'Today' && t.status !== 'done');
  const doneTasks  = MOCK_TASKS.filter(t => t.status === 'done').length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Greeting */}
      <div style={{
        background: 'linear-gradient(135deg, rgba(0,192,127,0.1) 0%, rgba(0,192,127,0.03) 100%)',
        border: '1px solid rgba(0,192,127,0.2)',
        borderRadius: 10,
        padding: '20px 24px',
      }}>
        <div style={{ fontSize: 13, color: 'var(--text-tertiary)', marginBottom: 4 }}>{today}</div>
        <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>
          {greeting}, Vineet 👋
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
          You have <strong style={{ color: '#ff9500' }}>{todayTasks.length} actions</strong> due today.
          North Star: <strong style={{ color: 'var(--accent)' }}>$10K net/mo by June 25</strong>.
        </div>
      </div>

      {/* KPI row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        {[
          { label: 'Days to Target', value: '30', color: '#ff9500', sub: 'June 25, 2026' },
          { label: 'Tasks Done Today', value: `${doneTasks}`, color: 'var(--accent)', sub: `of ${MOCK_TASKS.length} total` },
          { label: 'Active Deals', value: '3', color: '#4d9fff', sub: 'EF + Flippa' },
          { label: 'MRR', value: '$0', color: '#ff3b30', sub: 'Target: $10K' },
        ].map(kpi => (
          <div key={kpi.label} style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 8,
            padding: '16px',
            textAlign: 'center',
          }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: kpi.color, fontFamily: 'var(--font-mono)' }}>
              {kpi.value}
            </div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-primary)', marginTop: 4 }}>{kpi.label}</div>
            <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 2 }}>{kpi.sub}</div>
          </div>
        ))}
      </div>

      {/* Today's actions */}
      <div>
        <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', letterSpacing: '0.05em', marginBottom: 10 }}>
          TODAY'S PRIORITY ACTIONS
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {todayTasks.map(task => (
            <div key={task.id} style={{
              display: 'flex', alignItems: 'center', gap: 12,
              background: 'var(--surface)', border: '1px solid var(--border)',
              borderLeft: `3px solid ${PRIORITY_COLOR[task.priority]}`,
              borderRadius: 6, padding: '10px 14px',
            }}>
              <span style={{
                fontSize: 9, fontWeight: 700, letterSpacing: '0.05em',
                color: STATUS_COLOR[task.status],
                background: `${STATUS_COLOR[task.status]}15`,
                padding: '2px 7px', borderRadius: 4,
                whiteSpace: 'nowrap',
              }}>
                {STATUS_LABEL[task.status].toUpperCase()}
              </span>
              <span style={{ flex: 1, fontSize: 13, color: 'var(--text-primary)' }}>{task.title}</span>
              {task.due && (
                <span style={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>
                  {task.due}
                </span>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Thu calendar callout */}
      <div style={{
        background: 'rgba(255,149,0,0.06)', border: '1px solid rgba(255,149,0,0.25)',
        borderRadius: 8, padding: '14px 18px',
      }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: '#ff9500', letterSpacing: '0.06em', marginBottom: 8 }}>
          📅 THURSDAY MAY 28 — CRITICAL DAY
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {[
            { time: '9:00 AM', label: 'GovCon Status — Jay Prasad', link: 'https://meet.google.com/vjb-tgox-eoi' },
            { time: '11:00 AM', label: '🔴 Speaker Kit Masterclass — Leadr (Signature Talk deadline)', link: 'https://us02web.zoom.us/j/87443403414' },
            { time: '1:15 PM', label: 'Storeys f/u — Gabriela Perez (Otter PR)', link: 'https://meet.google.com/smd-tyzh-pgq' },
          ].map(ev => (
            <div key={ev.time} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: '#ff9500', minWidth: 60 }}>{ev.time}</span>
              <span style={{ fontSize: 12, color: 'var(--text-primary)', flex: 1 }}>{ev.label}</span>
              <a href={ev.link} target="_blank" rel="noopener noreferrer"
                style={{ fontSize: 10, color: '#4d9fff', textDecoration: 'none', whiteSpace: 'nowrap' }}>
                Join →
              </a>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}

/* ─────────────────────────────────────────
   TASKS TAB
───────────────────────────────────────── */
function TasksTab() {
  const [tasks, setTasks] = useState<UserTask[]>(MOCK_TASKS);
  const [filter, setFilter] = useState<'all' | 'todo' | 'in_progress' | 'done'>('all');

  const filtered = filter === 'all' ? tasks : tasks.filter(t => t.status === filter);
  const counts = {
    all: tasks.length,
    todo: tasks.filter(t => t.status === 'todo').length,
    in_progress: tasks.filter(t => t.status === 'in_progress').length,
    done: tasks.filter(t => t.status === 'done').length,
  };

  const cycle = (task: UserTask) => {
    const next: Record<UserTask['status'], UserTask['status']> = {
      todo: 'in_progress', in_progress: 'done', done: 'todo',
    };
    setTasks(prev => prev.map(t => t.id === task.id ? { ...t, status: next[t.status] } : t));
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Filter pills */}
      <div style={{ display: 'flex', gap: 6 }}>
        {(['all', 'todo', 'in_progress', 'done'] as const).map(f => (
          <button key={f} onClick={() => setFilter(f)} style={{
            padding: '5px 12px', borderRadius: 20, fontSize: 11, fontWeight: 600,
            cursor: 'pointer', border: 'none', transition: 'all 0.15s',
            background: filter === f ? 'var(--accent)' : 'var(--surface)',
            color: filter === f ? '#000' : 'var(--text-secondary)',
            outline: filter === f ? 'none' : '1px solid var(--border)',
          }}>
            {f === 'all' ? 'All' : f === 'in_progress' ? 'In Progress' : f.charAt(0).toUpperCase() + f.slice(1)} ({counts[f]})
          </button>
        ))}
      </div>

      {/* Task list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {filtered.map(task => (
          <div key={task.id} style={{
            display: 'flex', alignItems: 'center', gap: 12,
            background: task.status === 'done' ? 'rgba(255,255,255,0.02)' : 'var(--surface)',
            border: '1px solid var(--border)',
            borderLeft: `3px solid ${PRIORITY_COLOR[task.priority]}`,
            borderRadius: 6, padding: '10px 14px',
            opacity: task.status === 'done' ? 0.55 : 1,
          }}>
            {/* Checkbox */}
            <button onClick={() => cycle(task)} style={{
              width: 18, height: 18, borderRadius: 4, flexShrink: 0,
              border: `2px solid ${STATUS_COLOR[task.status]}`,
              background: task.status === 'done' ? STATUS_COLOR.done : 'transparent',
              cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              {task.status === 'done' && <span style={{ fontSize: 10, color: '#000' }}>✓</span>}
              {task.status === 'in_progress' && <span style={{ fontSize: 8, color: '#ff9500' }}>▶</span>}
            </button>

            <span style={{
              flex: 1, fontSize: 13, color: 'var(--text-primary)',
              textDecoration: task.status === 'done' ? 'line-through' : 'none',
            }}>
              {task.title}
            </span>

            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {task.due && (
                <span style={{ fontSize: 10, color: task.due === 'Today' ? '#ff9500' : 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
                  {task.due}
                </span>
              )}
              <span style={{
                fontSize: 9, fontWeight: 700, letterSpacing: '0.05em',
                color: PRIORITY_COLOR[task.priority],
                background: `${PRIORITY_COLOR[task.priority]}15`,
                padding: '2px 6px', borderRadius: 4,
              }}>
                {task.priority.toUpperCase()}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────
   GOALS TAB
───────────────────────────────────────── */
function GoalsTab() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
        30-day sprint · North Star: <strong style={{ color: 'var(--accent)' }}>$10K net/month by June 25, 2026</strong>
      </div>
      {MOCK_GOALS.map(goal => {
        const p = pct(goal.current, goal.target);
        return (
          <div key={goal.id} style={{
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 8, padding: '16px 18px',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10 }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{goal.title}</span>
              <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: goal.color, fontWeight: 700 }}>
                {goal.unit}{goal.current.toLocaleString()} / {goal.unit}{goal.target.toLocaleString()}
              </span>
            </div>
            {/* Progress bar */}
            <div style={{ height: 8, background: 'var(--bg)', borderRadius: 4, overflow: 'hidden' }}>
              <div style={{
                height: '100%', width: `${p}%`, background: goal.color,
                borderRadius: 4, transition: 'width 0.6s ease',
                minWidth: p > 0 ? 4 : 0,
              }} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6 }}>
              <span style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
                {p === 0 ? 'Not started' : `${p}% complete`}
              </span>
              <span style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
                {goal.target - goal.current} {goal.unit ? goal.unit : 'units'} to go
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ─────────────────────────────────────────
   INSIGHTS TAB
───────────────────────────────────────── */
function InsightsTab() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {MOCK_INSIGHTS.map(insight => (
        <div key={insight.id} style={{
          background: 'var(--surface)',
          borderLeft: `3px solid ${INSIGHT_COLOR[insight.type]}`,
          border: '1px solid var(--border)',
          borderRadius: 8, padding: '14px 16px',
          display: 'flex', gap: 12, alignItems: 'flex-start',
        }}>
          <span style={{ fontSize: 18, flexShrink: 0, marginTop: 2 }}>{INSIGHT_ICON[insight.type]}</span>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{insight.title}</span>
              <span style={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>{insight.time}</span>
            </div>
            <p style={{ fontSize: 12, color: 'var(--text-secondary)', margin: 0, lineHeight: 1.5 }}>{insight.body}</p>
          </div>
          <span style={{
            fontSize: 9, fontWeight: 700, letterSpacing: '0.05em',
            color: INSIGHT_COLOR[insight.type],
            background: `${INSIGHT_COLOR[insight.type]}15`,
            padding: '2px 7px', borderRadius: 4, flexShrink: 0,
            alignSelf: 'flex-start',
          }}>
            {insight.type.toUpperCase()}
          </span>
        </div>
      ))}
    </div>
  );
}

/* ─────────────────────────────────────────
   PROFILE TAB
───────────────────────────────────────── */
function ProfileTab() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 520 }}>
      {/* Avatar card */}
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 10, padding: '20px 24px',
        display: 'flex', alignItems: 'center', gap: 18,
      }}>
        <div style={{
          width: 56, height: 56, borderRadius: '50%',
          background: 'linear-gradient(135deg, #00C07F, #4d9fff)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 22, fontWeight: 700, color: '#fff', flexShrink: 0,
        }}>V</div>
        <div>
          <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>Vineet Ravi</div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>Mangotec LLC · Los Angeles, CA</div>
          <div style={{ fontSize: 11, color: 'var(--accent)', marginTop: 4, fontFamily: 'var(--font-mono)' }}>
            ONE MAN ARMY
          </div>
        </div>
      </div>

      {/* Config fields */}
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
        <div style={{ padding: '12px 18px', borderBottom: '1px solid var(--border)', fontSize: 11, fontWeight: 700, color: 'var(--text-tertiary)', letterSpacing: '0.05em' }}>
          VOICE DNA — user_profile.json
        </div>
        {[
          { key: 'tone', value: 'Direct, builder, no fluff' },
          { key: 'north_star', value: '$10K net/mo by June 25' },
          { key: 'audience', value: 'Founders, operators, solopreneurs' },
          { key: 'brand', value: 'Vineet Ravi · eva.mangotec.ai' },
          { key: 'frame', value: 'ONE MAN ARMY' },
        ].map((row, i) => (
          <div key={row.key} style={{
            display: 'flex', alignItems: 'center', gap: 16,
            padding: '10px 18px',
            background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)',
            borderBottom: '1px solid var(--border-light)',
          }}>
            <span style={{ fontSize: 11, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', minWidth: 100 }}>{row.key}</span>
            <span style={{ fontSize: 12, color: 'var(--text-primary)' }}>{row.value}</span>
          </div>
        ))}
      </div>

      <div style={{
        padding: '12px 16px', background: 'rgba(77,159,255,0.06)',
        border: '1px solid rgba(77,159,255,0.2)', borderRadius: 8,
        fontSize: 11, color: 'var(--text-tertiary)', lineHeight: 1.6,
      }}>
        Voice DNA is loaded from <code style={{ color: '#4d9fff' }}>~/.eva/user_profile.json</code> at runtime.
        Each white-label install gets its own profile — loosely coupled, never baked in.
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────
   MAIN EXPORT
───────────────────────────────────────── */
export function UserPanel() {
  const [activeTab, setActiveTab] = useState<UserTab>('dashboard');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

      {/* Top nav bar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 2,
        padding: '0 32px',
        borderBottom: '1px solid var(--border)',
        background: 'var(--bg)',
        flexShrink: 0,
      }}>
        {USER_TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              display: 'flex', alignItems: 'center', gap: 7,
              padding: '14px 16px',
              fontSize: 13, fontWeight: 600,
              border: 'none',
              borderBottom: activeTab === tab.id ? '2px solid var(--accent)' : '2px solid transparent',
              background: 'transparent',
              color: activeTab === tab.id ? 'var(--text-primary)' : 'var(--text-tertiary)',
              cursor: 'pointer',
              marginBottom: -1,
              transition: 'color 0.15s',
            }}
          >
            <span style={{ fontSize: 15 }}>{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={{
        flex: 1, overflowY: 'auto',
        padding: '28px 32px',
        maxWidth: 900, margin: '0 auto', width: '100%',
      }}>
        {activeTab === 'dashboard' && <DashboardTab />}
        {activeTab === 'tasks'     && <TasksTab />}
        {activeTab === 'goals'     && <GoalsTab />}
        {activeTab === 'insights'  && <InsightsTab />}
        {activeTab === 'profile'   && <ProfileTab />}
      </div>
    </div>
  );
}
