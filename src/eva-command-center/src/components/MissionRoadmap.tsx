import { useEffect, useRef, useState } from 'react';

/* ─────────────────────────────────────────────────────
   TYPES
───────────────────────────────────────────────────── */
type Status = 'done' | 'now' | 'pending' | 'target' | 'northstar';
type Lane = 'product' | 'acquire' | 'revenue' | 'infra';

interface Milestone {
  date: string;
  label: string;
  lane: Lane;
  side: 'above' | 'below';
  status: Status;
  title: string;
  desc: string;
}

/* ─────────────────────────────────────────────────────
   DATA
───────────────────────────────────────────────────── */
const TODAY = '2026-05-26';
const SPRINT_START = '2026-05-01';
const DEADLINE = '2026-06-25';

const MILESTONES: Milestone[] = [
  // EVA Product
  { date:'2026-05-01', label:'Logger',         lane:'product', side:'above', status:'done',
    title:'EVA Logger Module', desc:'Context API on port 8765. Activity logging foundation.' },
  { date:'2026-05-10', label:'Command Center', lane:'product', side:'above', status:'done',
    title:'EVA Command Center v0.7', desc:'React dashboard live at eva.mangotec.ai.' },
  { date:'2026-05-20', label:'Pathfinder',     lane:'product', side:'above', status:'done',
    title:'PathfinderLeads + GLŌSSAI', desc:'Incubator tab + GLŌSSAI panel wired into EVA nav.' },
  { date:'2026-05-26', label:'▶ HERE',          lane:'product', side:'above', status:'now',
    title:'You Are Here — May 26', desc:'DB pipeline building. Waitlist live. LinkedIn post ready.' },
  { date:'2026-06-05', label:'Voice Module',   lane:'product', side:'above', status:'pending',
    title:'Voice Interface (ElevenLabs)', desc:'Flash v2.5 integration. Awaiting API key.' },
  { date:'2026-06-15', label:'Showreel',       lane:'product', side:'above', status:'pending',
    title:'Showreel / Demo Agent', desc:'Script → ElevenLabs → HeyGen → YouTube pipeline.' },
  { date:'2026-06-25', label:'v1.0 Ship',      lane:'product', side:'above', status:'target',
    title:'EVA v1.0 Shipped', desc:'Full stack: voice + daily brief + deal scout + Pathfinder.' },

  // Acquisition
  { date:'2026-05-15', label:'Deal Scout',     lane:'acquire', side:'below', status:'done',
    title:'Deal Scout Active', desc:'Empire Flippers + Flippa pipeline live. USA filter active.' },
  { date:'2026-05-26', label:'Flippa #12197',  lane:'acquire', side:'below', status:'now',
    title:'Flippa #12197961 Outreach', desc:'Digital Wellness SaaS Michigan. $9,154 net/mo. Message drafted — send today.' },
  { date:'2026-06-05', label:'LOI / DD',       lane:'acquire', side:'below', status:'pending',
    title:'Letter of Intent / Due Diligence', desc:'First serious deal → LOI stage. USA-only, health/wellness/SaaS.' },
  { date:'2026-06-25', label:'Deal Closed',    lane:'acquire', side:'below', status:'target',
    title:'Deal Closed', desc:'Health / Wellness / Longevity SaaS acquired — or RCFE under contract.' },

  // Revenue
  { date:'2026-05-26', label:'Waitlist Live',  lane:'revenue', side:'above', status:'now',
    title:'EVA Waitlist Live', desc:'eva-waitlist.mangotec.ai collecting signups. Neon DB pending.' },
  { date:'2026-06-01', label:'First Paying',   lane:'revenue', side:'above', status:'pending',
    title:'First Paying Customer', desc:'$49/mo Starter or $500/mo Operator. Target: 5 in first week.' },
  { date:'2026-06-10', label:'$1K MRR',        lane:'revenue', side:'above', status:'pending',
    title:'$1,000 MRR Milestone', desc:'20× Starter or 2× Operator. First validation signal.' },
  { date:'2026-06-25', label:'$10K MRR',       lane:'revenue', side:'above', status:'target',
    title:'$10,000 MRR Target', desc:'200× Starter, 20× Operator, or blended. North Star achieved.' },

  // Infra / DB
  { date:'2026-05-10', label:'3-Tier DB',      lane:'infra', side:'below', status:'done',
    title:'3-Tier Database Architecture', desc:'PostgreSQL (L1) + Qdrant (L2) + ArcadeDB (L3) deployed.' },
  { date:'2026-05-24', label:'Schema v2',      lane:'infra', side:'below', status:'done',
    title:'incubator_leads Schema', desc:'Postgres L1 — incubator_leads table added to 01_schema.sql.' },
  { date:'2026-05-26', label:'Neon Setup',     lane:'infra', side:'below', status:'now',
    title:'Neon DB — Vineet Action', desc:'neon.tech → create project → NEON_DATABASE_URL → Vercel env → redeploy.' },
  { date:'2026-06-01', label:'Autostart',      lane:'infra', side:'below', status:'pending',
    title:'EVA Mac Autostart', desc:'5 modules auto-starting: logger, deal-scout, content-engine, pathfinder, channels.' },
];

const PRIORITY_ITEMS = [
  { tier:'P1', title:'Neon DB Setup',         meta:'neon.tech → NEON_DATABASE_URL → Vercel → redeploy waitlist', badge:'Vineet Action', badgeType:'blocker' as const },
  { tier:'P1', title:'LinkedIn Post',          meta:'Copy written. Own-post comment drafted. 5 min to post.', badge:'Ready', badgeType:'ready' as const },
  { tier:'P1', title:'EVA Mac Services',       meta:'5 modules offline. Major blocker for logging + monetization.', badge:'Blocked', badgeType:'blocker' as const },
  { tier:'P1', title:'Flippa Outreach',        meta:'#12197961 · $9,154/mo · Digital Wellness SaaS Michigan. Draft ready.', badge:'Send Today', badgeType:'ready' as const },
  { tier:'P1', title:'Thu May 28 — Full Day',  meta:'9am GovCon · 11am Speaker Kit DEADLINE · 1:15pm Storeys PR', badge:'48h', badgeType:'urgent' as const },
  { tier:'P1', title:'Vercel Deploy + GitHub', meta:'PathfinderLeads + GlossaiPanel → build → deploy → push Mangotec333/Eva', badge:'In Progress', badgeType:'active' as const },
  { tier:'P2', title:'Voice Module',           meta:'ElevenLabs Flash v2.5. Awaiting API key from Vineet.', badge:'Awaiting Key', badgeType:'pending' as const },
  { tier:'P2', title:'Showreel Agent',         meta:'Script → ElevenLabs → HeyGen → YouTube. Unblocked by ElevenLabs key.', badge:'P2 Queue', badgeType:'pending' as const },
  { tier:'P2', title:'GLŌSSAI Signups → Pathfinder', meta:'Wire Lovable signups → Pathfinder tagged source:glossai.', badge:'Live on Lovable', badgeType:'active' as const },
];

/* ─────────────────────────────────────────────────────
   DATE UTILS
───────────────────────────────────────────────────── */
function daysBetween(a: string, b: string) {
  return Math.round((new Date(b).getTime() - new Date(a).getTime()) / 86400000);
}
const daysLeft = daysBetween(TODAY, DEADLINE);
const sprintTotal = daysBetween(SPRINT_START, DEADLINE);
const sprintElapsed = daysBetween(SPRINT_START, TODAY);
const sprintPct = Math.round((sprintElapsed / sprintTotal) * 100);

/* ─────────────────────────────────────────────────────
   STATUS CONFIG
───────────────────────────────────────────────────── */
const STATUS_CFG: Record<Status, { color: string; bg: string; border: string; label: string }> = {
  done:      { color: '#00995f', bg: '#e6f9f3', border: '#b3eddb', label: '✓ Done' },
  now:       { color: '#ff3b30', bg: '#fff0ef', border: '#ffbdba', label: '▶ Active Now' },
  pending:   { color: '#e65100', bg: '#fff3e0', border: '#ffd7b0', label: '◦ Pending' },
  target:    { color: '#007aff', bg: '#e8f4ff', border: '#b3d7ff', label: '◎ Target' },
  northstar: { color: '#7d4fc1', bg: '#f3ecff', border: '#cfb3f5', label: '★ North Star' },
};

const LANE_CFG: Record<Lane, { label: string; color: string }> = {
  product: { label: 'EVA Product',   color: '#00C07F' },
  acquire: { label: 'Acquisition',   color: '#ff9500' },
  revenue: { label: 'Revenue',       color: '#007aff' },
  infra:   { label: 'Infra / DB',    color: '#7d4fc1' },
};

const BADGE_STYLES: Record<string, { bg: string; color: string }> = {
  blocker: { bg: '#fff0ef', color: '#ff3b30' },
  ready:   { bg: '#e6f9f3', color: '#00995f' },
  urgent:  { bg: '#fff0ef', color: '#ff3b30' },
  active:  { bg: '#fff3e0', color: '#e65100' },
  pending: { bg: '#f5f5f7', color: '#6e6e73' },
};

/* ─────────────────────────────────────────────────────
   TIMELINE GEOMETRY
───────────────────────────────────────────────────── */
const TL_START = new Date('2026-05-01').getTime();
const TL_END   = new Date('2026-07-01').getTime();
const TL_RANGE = TL_END - TL_START;
const TL_WIDTH = 820; // px
function dateToX(d: string) {
  return Math.round(((new Date(d).getTime() - TL_START) / TL_RANGE) * TL_WIDTH);
}

const DATE_TICKS = [
  { d:'2026-05-01', l:'May 1' },
  { d:'2026-05-15', l:'May 15' },
  { d:'2026-05-26', l:'May 26' },
  { d:'2026-06-01', l:'Jun 1' },
  { d:'2026-06-15', l:'Jun 15' },
  { d:'2026-06-25', l:'Jun 25' },
];

const LANE_ORDER: Lane[] = ['product', 'acquire', 'revenue', 'infra'];
const LANE_H = 72; // px per lane row
const HEADER_H = 28; // date axis height

/* ─────────────────────────────────────────────────────
   TOOLTIP COMPONENT
───────────────────────────────────────────────────── */
interface TooltipState {
  visible: boolean;
  x: number;
  y: number;
  m: Milestone | null;
}

/* ─────────────────────────────────────────────────────
   MAIN COMPONENT
───────────────────────────────────────────────────── */
export function MissionRoadmap() {
  const [tooltip, setTooltip] = useState<TooltipState>({ visible: false, x: 0, y: 0, m: null });
  const [activeTab, setActiveTab] = useState<'timeline' | 'priorities'>('timeline');
  const scrollRef = useRef<HTMLDivElement>(null);

  // Scroll timeline to today on mount
  useEffect(() => {
    if (activeTab === 'timeline' && scrollRef.current) {
      const todayX = dateToX(TODAY);
      scrollRef.current.scrollLeft = Math.max(0, todayX - 120);
    }
  }, [activeTab]);

  /* ── Progress bars ── */
  const ProgressBar = ({ pct, color }: { pct: number; color: string }) => (
    <div style={{ height: 4, background: '#f0f0f5', borderRadius: 9999, overflow: 'hidden', marginTop: 8 }}>
      <div
        style={{
          height: '100%', width: `${pct}%`, borderRadius: 9999,
          background: color, transition: 'width 1.2s cubic-bezier(0.16,1,0.3,1)',
        }}
      />
    </div>
  );

  /* ── Node dot ── */
  const NodeDot = ({ status, size = 12 }: { status: Status; size?: number }) => {
    const cfg = STATUS_CFG[status];
    const isNow = status === 'now';
    return (
      <div
        style={{
          width: size, height: size, borderRadius: '50%',
          background: status === 'pending' ? 'transparent' : cfg.color,
          border: `2px solid ${cfg.color}`,
          boxShadow: isNow ? `0 0 8px ${cfg.color}40` : undefined,
          flexShrink: 0,
          animation: isNow ? 'eva-pulse 2.5s ease-in-out infinite' : undefined,
        }}
      />
    );
  };

  /* ── Timeline SVG ── */
  const renderTimeline = () => {
    const totalH = HEADER_H + LANE_ORDER.length * LANE_H + 16;

    return (
      <div ref={scrollRef} style={{ overflowX: 'auto', overflowY: 'visible', paddingBottom: 8 }}>
        <div style={{ position: 'relative', width: TL_WIDTH + 80, minWidth: TL_WIDTH + 80, height: totalH + 20, paddingLeft: 40, paddingRight: 40 }}>

          {/* ── Date axis ── */}
          {DATE_TICKS.map(({ d, l }) => {
            const x = dateToX(d) + 40;
            const isToday = d === TODAY;
            return (
              <div key={d} style={{ position: 'absolute', left: x, top: 0, transform: 'translateX(-50%)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
                <span style={{ fontSize: 9, fontWeight: isToday ? 700 : 500, color: isToday ? '#ff3b30' : '#aeaeb2', letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>
                  {l}{isToday ? ' ▼' : ''}
                </span>
                <div style={{ width: 1, height: 6, background: isToday ? '#ff3b30' : '#e5e5ea' }} />
              </div>
            );
          })}

          {/* ── Lane rows ── */}
          {LANE_ORDER.map((lane, li) => {
            const y = HEADER_H + li * LANE_H;
            const laneMs = MILESTONES.filter(m => m.lane === lane).sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
            const cfg = LANE_CFG[lane];

            return (
              <div key={lane} style={{ position: 'absolute', left: 0, right: 0, top: y, height: LANE_H }}>
                {/* Row background stripe */}
                <div style={{
                  position: 'absolute', left: 0, right: 0, top: 0, height: LANE_H,
                  background: li % 2 === 0 ? 'transparent' : 'rgba(0,0,0,0.015)',
                  borderTop: `1px solid #f0f0f5`,
                }} />

                {/* Today line */}
                <div style={{
                  position: 'absolute',
                  left: dateToX(TODAY) + 40,
                  top: 0, bottom: 0, width: 1,
                  background: '#ff3b30',
                  opacity: 0.5,
                  zIndex: 5,
                }} />

                {/* Connector lines */}
                {laneMs.map((m, mi) => {
                  if (mi === laneMs.length - 1) return null;
                  const next = laneMs[mi + 1];
                  const x1 = dateToX(m.date) + 40;
                  const x2 = dateToX(next.date) + 40;
                  const isDone = m.status === 'done' && next.status === 'done';
                  const isActive = m.status === 'done' && (next.status === 'pending' || next.status === 'now');
                  return (
                    <div
                      key={`conn-${mi}`}
                      style={{
                        position: 'absolute',
                        left: x1, top: LANE_H / 2 - 1,
                        width: x2 - x1, height: 2,
                        background: isDone
                          ? cfg.color
                          : isActive
                            ? `linear-gradient(90deg, ${cfg.color}, #e5e5ea)`
                            : '#e5e5ea',
                        opacity: isDone ? 0.6 : isActive ? 0.7 : 0.5,
                        borderRadius: 1,
                        zIndex: 4,
                      }}
                    />
                  );
                })}

                {/* Milestone nodes */}
                {laneMs.map(m => {
                  const x = dateToX(m.date) + 40;
                  const scfg = STATUS_CFG[m.status];
                  const isAbove = m.side === 'above';
                  const isNow = m.status === 'now';

                  return (
                    <div
                      key={`${m.lane}-${m.date}`}
                      style={{ position: 'absolute', left: x, top: 0, bottom: 0, display: 'flex', alignItems: 'center', zIndex: 10, cursor: 'pointer' }}
                      onMouseEnter={e => setTooltip({ visible: true, x: e.clientX, y: e.clientY, m })}
                      onMouseMove={e => setTooltip(t => ({ ...t, x: e.clientX, y: e.clientY }))}
                      onMouseLeave={() => setTooltip(t => ({ ...t, visible: false }))}
                    >
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', transform: 'translateX(-50%)', gap: 2 }}>
                        {/* Label above */}
                        {isAbove && (
                          <span style={{
                            fontSize: 9, fontWeight: 500, color: isNow ? scfg.color : '#6e6e73',
                            whiteSpace: 'nowrap', letterSpacing: '0.02em',
                            maxWidth: 64, textAlign: 'center', lineHeight: 1.2,
                          }}>
                            {m.label}
                          </span>
                        )}

                        {/* Dot */}
                        <div style={{
                          width: isNow ? 14 : 12,
                          height: isNow ? 14 : 12,
                          borderRadius: '50%',
                          background: m.status === 'pending' ? 'transparent' : scfg.color,
                          border: `2px solid ${scfg.color}`,
                          boxShadow: isNow ? `0 0 0 3px ${scfg.color}20` : undefined,
                          transition: 'transform 0.15s ease, box-shadow 0.15s ease',
                          flexShrink: 0,
                        }} />

                        {/* Label below */}
                        {!isAbove && (
                          <span style={{
                            fontSize: 9, fontWeight: 500, color: isNow ? scfg.color : '#6e6e73',
                            whiteSpace: 'nowrap', letterSpacing: '0.02em',
                            maxWidth: 64, textAlign: 'center', lineHeight: 1.2,
                          }}>
                            {m.label}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            );
          })}

          {/* Lane labels (left, sticky-ish) */}
          {LANE_ORDER.map((lane, li) => {
            const y = HEADER_H + li * LANE_H + LANE_H / 2;
            return null; // labels rendered outside in the label column
            return y;
          })}
        </div>
      </div>
    );
  };

  /* ─────────────────────────
     RENDER
  ───────────────────────── */
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* ── Pulse keyframe injection ── */}
      <style>{`
        @keyframes eva-pulse {
          0%,100% { box-shadow: 0 0 0 0 #ff3b3040; }
          50%      { box-shadow: 0 0 0 5px #ff3b3020; }
        }
        @keyframes eva-fill {
          from { width: 0% }
        }
      `}</style>

      {/* ── North Star Banner ── */}
      <div className="eva-card" style={{
        background: 'linear-gradient(135deg, #f3ecff 0%, #e8f4ff 100%)',
        border: '1px solid #cfb3f5',
        padding: '20px 24px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16,
      }}>
        <div>
          <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#7d4fc1', marginBottom: 4 }}>
            ★ North Star
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, color: '#1d1d1f', letterSpacing: '-0.02em', marginBottom: 4 }}>
            $10K Net/Month + Deal Closed
          </div>
          <div style={{ fontSize: 12, color: '#6e6e73', lineHeight: 1.5 }}>
            Health / Wellness / Longevity SaaS (USA) — or RCFE closed · $200K HELOC @ 9.5%
          </div>
        </div>
        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <div style={{ fontSize: 40, fontWeight: 700, color: '#007aff', lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>
            {daysLeft}
          </div>
          <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#aeaeb2', marginTop: 2 }}>
            Days to Jun 25
          </div>
        </div>
      </div>

      {/* ── KPI Cards row ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16 }}>
        {/* Mission */}
        <div className="eva-card" style={{ padding: '18px 20px', borderTop: '3px solid #7d4fc1' }}>
          <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#aeaeb2', marginBottom: 6 }}>Mission</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: '#7d4fc1', marginBottom: 4 }}>$1B Impact</div>
          <div style={{ fontSize: 12, color: '#6e6e73', lineHeight: 1.5 }}>1 million lives better. EVA as the OS for the solo builder.</div>
        </div>

        {/* Position */}
        <div className="eva-card" style={{ padding: '18px 20px', borderTop: '3px solid #ff3b30' }}>
          <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#aeaeb2', marginBottom: 6 }}>📍 You Are Here · May 26</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: '#ff3b30', marginBottom: 4 }}>Sprint Active</div>
          <div style={{ fontSize: 12, color: '#6e6e73', marginBottom: 6 }}>Waitlist live · DB pipeline · LinkedIn post ready</div>
          <ProgressBar pct={sprintPct} color="linear-gradient(90deg, #ff3b30, #ff9500)" />
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, fontSize: 10, color: '#aeaeb2' }}>
            <span>May 1</span><span>{sprintPct}% of sprint</span><span>Jun 25</span>
          </div>
        </div>

        {/* Target */}
        <div className="eva-card" style={{ padding: '18px 20px', borderTop: '3px solid #00C07F' }}>
          <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#aeaeb2', marginBottom: 6 }}>30-Day Target · Jun 25</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: '#00C07F', marginBottom: 4 }}>$10K MRR</div>
          <div style={{ fontSize: 12, color: '#6e6e73', marginBottom: 6 }}>Deal acquired or RCFE closed · 200 paying users</div>
          <ProgressBar pct={3} color="#00C07F" />
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, fontSize: 10, color: '#aeaeb2' }}>
            <span>$0</span><span>~$0 today</span><span>$10K</span>
          </div>
        </div>
      </div>

      {/* ── Tab bar ── */}
      <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid #e5e5ea' }}>
        {(['timeline', 'priorities'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '10px 20px',
              fontSize: 13, fontWeight: 500,
              color: activeTab === tab ? '#00995f' : '#6e6e73',
              background: 'none', border: 'none', cursor: 'pointer',
              borderBottom: `2px solid ${activeTab === tab ? '#00C07F' : 'transparent'}`,
              marginBottom: -1,
              textTransform: 'capitalize',
              transition: 'color 0.15s ease',
            }}
          >
            {tab === 'timeline' ? '📅 Mission Timeline' : '🎯 Priority Stack'}
          </button>
        ))}
      </div>

      {/* ── TIMELINE TAB ── */}
      {activeTab === 'timeline' && (
        <div className="eva-card" style={{ padding: 0, overflow: 'hidden' }}>

          {/* Legend */}
          <div style={{ padding: '12px 20px', borderBottom: '1px solid #f0f0f5', display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
            {(Object.entries(STATUS_CFG) as [Status, typeof STATUS_CFG[Status]][]).map(([s, cfg]) => (
              <div key={s} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <NodeDot status={s} size={8} />
                <span style={{ fontSize: 10, fontWeight: 500, color: '#6e6e73', letterSpacing: '0.04em' }}>{cfg.label}</span>
              </div>
            ))}
          </div>

          {/* Lane labels + scroll area */}
          <div style={{ display: 'flex' }}>
            {/* Lane label column */}
            <div style={{ width: 120, flexShrink: 0, borderRight: '1px solid #f0f0f5', paddingTop: HEADER_H }}>
              {LANE_ORDER.map((lane, li) => {
                const cfg = LANE_CFG[lane];
                return (
                  <div
                    key={lane}
                    style={{
                      height: LANE_H,
                      display: 'flex', alignItems: 'center', gap: 6,
                      padding: '0 12px',
                      borderTop: li > 0 ? '1px solid #f0f0f5' : undefined,
                    }}
                  >
                    <div style={{ width: 6, height: 6, borderRadius: '50%', background: cfg.color, flexShrink: 0 }} />
                    <span style={{ fontSize: 10, fontWeight: 600, color: '#6e6e73', letterSpacing: '0.04em', textTransform: 'uppercase', lineHeight: 1.2 }}>
                      {cfg.label}
                    </span>
                  </div>
                );
              })}
            </div>

            {/* Scrollable timeline */}
            <div style={{ flex: 1, overflowX: 'auto', overflowY: 'visible', paddingBottom: 12 }}>
              <div style={{ position: 'relative', width: TL_WIDTH + 80, minWidth: TL_WIDTH + 80, paddingLeft: 40, paddingRight: 40 }}>

                {/* Date axis */}
                <div style={{ position: 'relative', height: HEADER_H }}>
                  {DATE_TICKS.map(({ d, l }) => {
                    const x = dateToX(d);
                    const isToday = d === TODAY;
                    return (
                      <div key={d} style={{ position: 'absolute', left: x + 40, transform: 'translateX(-50%)', top: 6, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
                        <span style={{ fontSize: 9, fontWeight: isToday ? 700 : 400, color: isToday ? '#ff3b30' : '#aeaeb2', letterSpacing: '0.05em', whiteSpace: 'nowrap' }}>
                          {l}{isToday ? ' ◀' : ''}
                        </span>
                        <div style={{ width: 1, height: 5, background: isToday ? '#ff3b30' : '#e5e5ea' }} />
                      </div>
                    );
                  })}
                </div>

                {/* Lane rows */}
                {LANE_ORDER.map((lane, li) => {
                  const laneMs = MILESTONES.filter(m => m.lane === lane)
                    .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
                  const cfg = LANE_CFG[lane];

                  return (
                    <div key={lane} style={{ position: 'relative', height: LANE_H, borderTop: '1px solid #f0f0f5' }}>
                      {/* Today vertical line */}
                      <div style={{
                        position: 'absolute', left: dateToX(TODAY) + 40,
                        top: 0, bottom: 0, width: 1,
                        background: '#ff3b30', opacity: 0.3, zIndex: 5,
                      }} />

                      {/* Connector lines */}
                      {laneMs.map((m, mi) => {
                        if (mi === laneMs.length - 1) return null;
                        const next = laneMs[mi + 1];
                        const x1 = dateToX(m.date) + 40;
                        const x2 = dateToX(next.date) + 40;
                        const isDone = m.status === 'done' && (next.status === 'done' || next.status === 'now');
                        const isActive = (m.status === 'done' || m.status === 'now') && (next.status === 'pending' || next.status === 'target');
                        return (
                          <div key={`c${mi}`} style={{
                            position: 'absolute',
                            left: x1, top: '50%', marginTop: -1,
                            width: x2 - x1, height: 2,
                            background: isDone ? cfg.color : isActive ? '#d1d1d6' : '#e5e5ea',
                            opacity: isDone ? 0.7 : isActive ? 0.5 : 0.4,
                            borderRadius: 1, zIndex: 4,
                          }} />
                        );
                      })}

                      {/* Nodes */}
                      {laneMs.map(m => {
                        const x = dateToX(m.date) + 40;
                        const scfg = STATUS_CFG[m.status];
                        const isNow = m.status === 'now';
                        const isAbove = m.side === 'above';

                        return (
                          <div
                            key={`${m.lane}-${m.date}`}
                            title={m.title}
                            style={{ position: 'absolute', left: x, top: 0, bottom: 0, display: 'flex', alignItems: 'center', zIndex: 10, cursor: 'pointer' }}
                            onMouseEnter={e => setTooltip({ visible: true, x: e.clientX, y: e.clientY, m })}
                            onMouseMove={e => setTooltip(t => ({ ...t, x: e.clientX, y: e.clientY }))}
                            onMouseLeave={() => setTooltip(t => ({ ...t, visible: false }))}
                          >
                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', transform: 'translateX(-50%)', gap: 3 }}>
                              {isAbove && (
                                <span style={{ fontSize: 8, fontWeight: isNow ? 700 : 500, color: isNow ? scfg.color : '#aeaeb2', whiteSpace: 'nowrap', maxWidth: 62, textAlign: 'center', lineHeight: 1.2 }}>
                                  {m.label}
                                </span>
                              )}
                              <div style={{
                                width: isNow ? 14 : 11,
                                height: isNow ? 14 : 11,
                                borderRadius: '50%',
                                background: m.status === 'pending' ? 'white' : scfg.color,
                                border: `2px solid ${scfg.color}`,
                                boxShadow: isNow ? `0 0 0 3px ${scfg.color}25` : undefined,
                                flexShrink: 0,
                                animation: isNow ? 'eva-pulse 2.5s ease-in-out infinite' : undefined,
                              }} />
                              {!isAbove && (
                                <span style={{ fontSize: 8, fontWeight: isNow ? 700 : 500, color: isNow ? scfg.color : '#aeaeb2', whiteSpace: 'nowrap', maxWidth: 62, textAlign: 'center', lineHeight: 1.2 }}>
                                  {m.label}
                                </span>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── PRIORITIES TAB ── */}
      {activeTab === 'priorities' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 14 }}>
          {PRIORITY_ITEMS.map((item, i) => {
            const bs = BADGE_STYLES[item.badgeType];
            const isP1 = item.tier === 'P1';
            return (
              <div
                key={i}
                className="eva-card"
                style={{
                  padding: '16px 18px',
                  borderLeft: `3px solid ${isP1 ? '#ff3b30' : '#ff9500'}`,
                  position: 'relative',
                }}
              >
                <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: isP1 ? '#ff3b30' : '#e65100', marginBottom: 6 }}>
                  {item.tier}
                </div>
                <div style={{ fontSize: 13, fontWeight: 600, color: '#1d1d1f', marginBottom: 5, lineHeight: 1.3 }}>
                  {item.title}
                </div>
                <div style={{ fontSize: 11, color: '#6e6e73', lineHeight: 1.5, marginBottom: 10 }}>
                  {item.meta}
                </div>
                <span style={{
                  display: 'inline-flex', alignItems: 'center', gap: 4,
                  fontSize: 10, fontWeight: 600, letterSpacing: '0.06em',
                  padding: '3px 8px', borderRadius: 100,
                  background: bs.bg, color: bs.color,
                }}>
                  {item.badge}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* ── Tooltip ── */}
      {tooltip.visible && tooltip.m && (() => {
        const m = tooltip.m;
        const scfg = STATUS_CFG[m.status];
        let left = tooltip.x + 14;
        let top = tooltip.y + 10;
        if (left + 260 > window.innerWidth) left = tooltip.x - 260 - 14;
        if (top + 140 > window.innerHeight) top = tooltip.y - 140 - 10;
        return (
          <div style={{
            position: 'fixed', left, top, zIndex: 9999,
            background: 'white', border: '1px solid #e5e5ea',
            borderRadius: 12, padding: '14px 16px', width: 240,
            boxShadow: '0 8px 32px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.06)',
            pointerEvents: 'none',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
              <NodeDot status={m.status} size={8} />
              <span style={{ fontSize: 10, fontWeight: 600, color: scfg.color, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                {scfg.label}
              </span>
            </div>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#1d1d1f', marginBottom: 5, lineHeight: 1.3 }}>
              {m.title}
            </div>
            <div style={{ fontSize: 11, color: '#6e6e73', lineHeight: 1.5 }}>
              {m.desc}
            </div>
            <div style={{ marginTop: 10, fontSize: 10, color: '#aeaeb2', fontVariantNumeric: 'tabular-nums' }}>
              {new Date(m.date).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}
            </div>
          </div>
        );
      })()}

    </div>
  );
}
