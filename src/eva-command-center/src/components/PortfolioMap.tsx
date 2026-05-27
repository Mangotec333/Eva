import { useState } from 'react';

/* ─────────────────────────────────────────
   TYPES
───────────────────────────────────────── */
type Tier = 1 | 2 | 3;
type CategoryKey = 'eva' | 'acquisition' | 'storeys' | 'glossai' | 'brand' | 'agency';

/* ─────────────────────────────────────────
   DATA
───────────────────────────────────────── */
const REVENUE_TIERS = [
  {
    tier: 1 as Tier,
    label: 'TIER 1',
    sublabel: 'Cash in < 7 Days',
    note: 'If you act today',
    color: 'var(--accent)',
    rows: [
      { n: '01', stream: 'EVA Morning Command', vehicle: 'Direct outreach to founders/operators', price: '$500/mo + $1,500 setup', action: 'DM 5 LinkedIn connections today. Script done, waitlist live.', urgency: 'today' },
      { n: '02', stream: 'AI Consulting / Fractional AI', vehicle: 'AI Growth Agency — existing network', price: '$3K–$5K/project', action: 'Email Gutha Kannan + 2 warm intros. Close by Friday.', urgency: 'today' },
      { n: '03', stream: 'Flippa Outreach → LOI', vehicle: 'Flippa #12197961 ($9,154 net/mo)', price: 'HELOC capital deployed', action: 'Message drafted. Send TODAY via Flippa contact form.', urgency: 'today' },
      { n: '04', stream: 'EVA Waitlist → Founding Member', vehicle: 'eva-waitlist.mangotec.ai', price: '$49/mo · $500/mo Operator', action: 'Publish LinkedIn post (copy ready). Drive first 20 signups.', urgency: 'today' },
      { n: '05', stream: 'GLŌSSAI Founding Member', vehicle: 'smart-beauty-guide.lovable.app', price: '$149 LTD / $19/mo', action: 'Post 1 beauty/wellness reel. Drive 10 founding signups.', urgency: 'week' },
    ],
  },
  {
    tier: 2 as Tier,
    label: 'TIER 2',
    sublabel: 'Cash in 2–4 Weeks',
    note: 'Build underway',
    color: '#ff9500',
    rows: [
      { n: '06', stream: 'EVA Enterprise Deals', vehicle: 'White-label EVA to agencies/operators', price: '$1,500/mo + $5K setup', action: 'Needs ElevenLabs key + showreel for pitch.', urgency: 'week' },
      { n: '07', stream: 'Storeys / RCFE Acquisition', vehicle: 'RCFE under contract', price: 'Asset cash flow post-close', action: 'Closing ongoing. Not fully in your control.', urgency: 'soon' },
      { n: '08', stream: 'Acquired Online Business', vehicle: 'Health/Wellness SaaS USA (EF/Flippa)', price: '$9K–$19K net/mo target', action: 'HELOC ready. Close 2–3 wks post-LOI.', urgency: 'week' },
      { n: '09', stream: 'EVA Showreel → Inbound', vehicle: 'YouTube + LinkedIn demo video', price: 'Top-of-funnel for all tiers', action: 'Needs ElevenLabs key + YouTube OAuth.', urgency: 'week' },
      { n: '10', stream: 'Signature Talk: The Hail Mary', vehicle: 'Leadr · Speaker Kit Masterclass', price: '$2K–$10K/engagement', action: 'Finalize Wed night. Present Thu 11am.', urgency: 'thu' },
    ],
  },
  {
    tier: 3 as Tier,
    label: 'TIER 3',
    sublabel: 'Cash in 30–90 Days',
    note: 'Infrastructure phase',
    color: '#4d9fff',
    rows: [
      { n: '11', stream: 'GLŌSSAI Full Product Launch', vehicle: 'Lovable.dev → full product build', price: '$19/mo SaaS', action: 'Landing live. Product UI placeholder. Needs ingredient engine.', urgency: 'later' },
      { n: '12', stream: 'EVA Pattern Engine / Data Moat', vehicle: 'Module 5 — nightly behavioral patterns', price: 'Upsell to Enterprise $3K+/mo', action: 'Module spec complete. Build in June.', urgency: 'later' },
      { n: '13', stream: 'LinkedIn Content → Inbound', vehicle: 'EVA Content Engine → nightly drafts', price: 'Feeds all other streams', action: 'Content engine built. Needs LinkedIn OAuth.', urgency: 'later' },
      { n: '14', stream: "Children's Book / IP", vehicle: 'Writing + publishing', price: 'Passive royalties', action: 'Parked. Revisit post-$10K.', urgency: 'parked' },
      { n: '15', stream: 'Algorithmic Trading', vehicle: 'Tabled for now', price: 'Passive capital growth', action: 'Revisit when base income secured.', urgency: 'parked' },
    ],
  },
];

const URGENCY_STYLE: Record<string, { label: string; color: string; bg: string }> = {
  today:  { label: 'TODAY',  color: '#00C07F', bg: 'rgba(0,192,127,0.12)' },
  thu:    { label: 'THU',    color: '#ff9500', bg: 'rgba(255,149,0,0.12)' },
  week:   { label: 'WEEK',   color: '#4d9fff', bg: 'rgba(77,159,255,0.12)' },
  soon:   { label: 'SOON',   color: '#8b949e', bg: 'rgba(139,148,158,0.1)' },
  later:  { label: 'LATER',  color: '#6e7681', bg: 'rgba(110,118,129,0.08)' },
  parked: { label: 'PARKED', color: '#484f58', bg: 'rgba(72,79,88,0.08)' },
};

const CATEGORIES: {
  key: CategoryKey;
  icon: string;
  title: string;
  color: string;
  desc: string;
  items: { label: string; status: string; statusColor: string; priority: string; note: string }[];
  footer?: string;
}[] = [
  {
    key: 'eva',
    icon: '⚡',
    title: 'EVA Platform',
    color: 'var(--accent)',
    desc: 'Core Product + Revenue Engine. AI-powered personal & business OS. Daily brief, deal scout, content engine, Pathfinder CRM.',
    items: [
      { label: 'Command Center (eva.mangotec.ai)', status: 'Live v0.8.1', statusColor: 'var(--accent)', priority: 'P0', note: 'All EVA tiers' },
      { label: 'Daily Morning Brief (cron)', status: 'Live', statusColor: 'var(--accent)', priority: 'P0', note: 'Retention / demo' },
      { label: 'Waitlist + Lead Pipeline', status: 'Neon DB not set', statusColor: '#ff9500', priority: 'P1', note: 'Vineet action needed' },
      { label: 'Pathfinder CRM', status: 'Built', statusColor: 'var(--accent)', priority: 'P1', note: 'Lead conversion' },
      { label: 'Voice Module (ElevenLabs)', status: 'Blocked — API key', statusColor: '#ff3b30', priority: 'P1', note: 'Enterprise upsell' },
      { label: 'Content Engine (port 8767)', status: 'Offline', statusColor: '#ff9500', priority: 'P1', note: 'LinkedIn → inbound' },
      { label: 'EVA Mac Services (all 5)', status: 'Offline', statusColor: '#ff3b30', priority: 'P1', note: 'Activity logging' },
      { label: 'EVA Onboarding + Voice DNA', status: 'Planned', statusColor: '#4d9fff', priority: 'P1', note: 'White-label unlock' },
      { label: 'Mission Roadmap tab', status: 'Built', statusColor: 'var(--accent)', priority: 'P2', note: 'Internal clarity' },
      { label: 'GLŌSSAI Panel', status: 'Built', statusColor: 'var(--accent)', priority: 'P2', note: 'Cross-sell' },
    ],
    footer: '$49/mo Starter · $500/mo Operator · $1,500/mo Enterprise · White-label (future)',
  },
  {
    key: 'acquisition',
    icon: '🎯',
    title: 'Business Acquisition',
    color: '#4d9fff',
    desc: 'Capital Deployment. Buy cash-flowing online businesses (Health/Wellness/SaaS, USA only) using $200K HELOC.',
    items: [
      { label: 'Flippa #12197961 — Wellness SaaS MI', status: 'Outreach drafted', statusColor: '#ff9500', priority: 'P1', note: 'Send TODAY' },
      { label: 'EF #88148 — Amazon FBA BW Brands', status: 'Video Intel 7.4/10', statusColor: '#4d9fff', priority: 'P2', note: 'Run DD checklist' },
      { label: 'EF #87872 — Digital Media', status: 'NDA stage', statusColor: '#ff9500', priority: 'P1', note: 'Follow up' },
      { label: 'Empire Flippers daily scan', status: 'Active', statusColor: 'var(--accent)', priority: 'P1', note: 'Check daily brief' },
      { label: 'Deal Scout (port 8766)', status: 'Offline', statusColor: '#ff3b30', priority: 'P1', note: 'Start Mac services' },
    ],
    footer: '$200K HELOC @ 9.5% (~$1,682/mo debt service)',
  },
  {
    key: 'storeys',
    icon: '🏢',
    title: 'Storeys / Real Estate',
    color: '#ff3b30',
    desc: 'Capital Event. Healthcare CRE play. RCFE under contract. Long-term capital event — not a near-term cash flow source.',
    items: [
      { label: 'RCFE under contract', status: 'Closing process', statusColor: '#ff9500', priority: 'P2', note: 'Not fully in your control' },
      { label: 'GovCon — Jay Prasad', status: 'Thu May 28 9am', statusColor: '#ff9500', priority: 'P1', note: 'Show up prepared' },
      { label: 'Storeys f/u — Gabriela Perez (PR)', status: 'Thu May 28 1:15pm', statusColor: '#ff9500', priority: 'P1', note: 'PR + positioning' },
      { label: 'Healthcare CRE research', status: 'Ongoing', statusColor: '#4d9fff', priority: 'P3', note: 'Post-RCFE close' },
    ],
  },
  {
    key: 'glossai',
    icon: '✨',
    title: 'GLŌSSAI',
    color: '#ff9500',
    desc: 'Consumer Brand — EVA Personal Stack. AI clean beauty / skincare ingredient analyzer. Top-of-funnel for non-operator audience.',
    items: [
      { label: 'Landing page', status: 'Live (Lovable.dev)', statusColor: 'var(--accent)', priority: 'P1', note: 'Drive traffic NOW' },
      { label: 'Product UI', status: 'Placeholder', statusColor: '#ff3b30', priority: 'P2', note: 'Needs ingredient engine' },
      { label: 'Founding member offer ($149 LTD)', status: 'Ready', statusColor: 'var(--accent)', priority: 'P1', note: 'Post 1 reel this week' },
      { label: 'Pathfinder integration', status: '10-min build', statusColor: '#4d9fff', priority: 'P2', note: 'Wire signups → CRM' },
      { label: 'Pricing: Free / $19/mo / $149 LTD', status: 'Set', statusColor: 'var(--accent)', priority: '—', note: '—' },
    ],
  },
  {
    key: 'brand',
    icon: '🎤',
    title: 'Brand / Authority',
    color: 'var(--accent)',
    desc: 'Inbound Flywheel. Vineet as the "ONE MAN ARMY" operator. LinkedIn first. Feeds all other categories.',
    items: [
      { label: 'LinkedIn post (EVA intro)', status: 'Written', statusColor: 'var(--accent)', priority: 'P1', note: 'Post TODAY' },
      { label: 'Signature Talk "The Hail Mary"', status: 'Finalize Wed', statusColor: '#ff9500', priority: 'P1', note: 'Thu 11am deadline' },
      { label: 'Speaker Kit Masterclass', status: 'Thu May 28 11am', statusColor: '#ff9500', priority: 'P1', note: 'Show up with deck' },
      { label: 'EVA Showreel (demo video)', status: 'P2 build', statusColor: '#4d9fff', priority: 'P2', note: 'ElevenLabs key needed' },
      { label: "Personal website", status: 'Parked', statusColor: '#6e7681', priority: 'P3', note: 'Post-revenue' },
      { label: "Children's Book", status: 'Parked', statusColor: '#6e7681', priority: 'P3', note: 'Revisit post-$10K' },
    ],
  },
  {
    key: 'agency',
    icon: '🤖',
    title: 'AI Growth Agency',
    color: '#4d9fff',
    desc: 'Consulting Income Bridge. Fractional AI consulting. Bridge income while EVA scales to $10K MRR.',
    items: [
      { label: 'Target: $3K–$5K in 30 days', status: 'NOT STARTED', statusColor: '#ff3b30', priority: 'P1', note: 'Email Gutha Kannan + 2 TODAY' },
      { label: 'Target: $10K/mo from 3 clients', status: 'June goal', statusColor: '#4d9fff', priority: 'P2', note: 'Pitch EVA as proof of work' },
      { label: 'Offer: Fractional AI Build', status: 'Defined', statusColor: 'var(--accent)', priority: 'P1', note: 'EVA is the case study' },
    ],
  },
];

const DASHBOARD_ROWS: { cat: string; cashNow: string; cashColor: string; stage: string; contribution: string }[] = [
  { cat: 'EVA Platform',        cashNow: '> YES',    cashColor: 'var(--accent)', stage: 'Building',       contribution: '$500–$3K MRR (first 5 users)' },
  { cat: 'Business Acquisition',cashNow: '> YES',    cashColor: 'var(--accent)', stage: 'Active pursuit', contribution: '$7K–$17K net/mo (if deal closes)' },
  { cat: 'Storeys / RCFE',      cashNow: '~ SOON',   cashColor: '#ff9500',       stage: 'Closing',        contribution: 'Capital event (not MRR)' },
  { cat: 'GLŌSSAI',             cashNow: '> YES',    cashColor: 'var(--accent)', stage: 'Live landing',   contribution: '$500–$1.5K (founding members)' },
  { cat: 'Brand / Authority',   cashNow: '^ FEEDS',  cashColor: '#4d9fff',       stage: 'Active',         contribution: 'Feeds all above' },
  { cat: 'AI Growth Agency',    cashNow: '> YES',    cashColor: 'var(--accent)', stage: 'Not started',    contribution: '$3K–$5K/mo consulting' },
];

const ONE_THING_ROWS: { cat: string; action: string; when: string; color: string }[] = [
  { cat: 'EVA Platform',         action: 'Set NEON_DATABASE_URL in Vercel + publish LinkedIn post', when: 'Today',     color: 'var(--accent)' },
  { cat: 'Acquisition',          action: 'Send Flippa #12197961 outreach message',                  when: 'Today',     color: '#4d9fff' },
  { cat: 'Storeys',              action: 'Show up prepared for Thu GovCon + Storeys calls',          when: 'Wed night', color: '#ff3b30' },
  { cat: 'GLŌSSAI',              action: 'Post 1 reel / story driving to founding member offer',    when: 'This week', color: '#ff9500' },
  { cat: 'Brand',                action: 'Finalize Signature Talk, post LinkedIn intro',            when: 'Wed + Thu', color: 'var(--accent)' },
  { cat: 'AI Agency',            action: 'Send 3 outreach emails to warm network',                  when: 'Today',     color: '#4d9fff' },
];

/* ─────────────────────────────────────────
   SUB-COMPONENTS
───────────────────────────────────────── */

function TierBadge({ label, sublabel, note, color }: { label: string; sublabel: string; note: string; color: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 10 }}>
      <span style={{ fontSize: 11, fontWeight: 700, color, fontFamily: 'var(--font-mono)', letterSpacing: '0.06em' }}>
        ● {label}
      </span>
      <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>{sublabel}</span>
      <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>— {note}</span>
    </div>
  );
}

function RevenueTable({ rows, accentColor, tierNum }: {
  rows: typeof REVENUE_TIERS[0]['rows'];
  accentColor: string;
  tierNum: Tier;
}) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ borderBottom: `1.5px solid ${accentColor}` }}>
            {['#', 'Stream', 'Vehicle', 'Price Point', 'Action / Blocker'].map((h, i) => (
              <th key={h} style={{
                padding: '7px 10px',
                textAlign: 'left',
                fontSize: 10,
                fontWeight: 700,
                color: 'var(--text-secondary)',
                letterSpacing: '0.04em',
                background: 'var(--surface-alt)',
                width: i === 0 ? 28 : i === 4 ? '32%' : 'auto',
              }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const urg = URGENCY_STYLE[row.urgency];
            return (
              <tr key={row.n} style={{ background: i % 2 === 0 ? 'var(--surface)' : '#1a2030' }}>
                <td style={{ padding: '8px 10px', color: accentColor, fontWeight: 700, fontFamily: 'var(--font-mono)', fontSize: 11, borderLeft: `3px solid ${accentColor}` }}>
                  {row.n}
                </td>
                <td style={{ padding: '8px 10px', color: 'var(--text-primary)', fontWeight: 600 }}>{row.stream}</td>
                <td style={{ padding: '8px 10px', color: 'var(--text-secondary)', fontSize: 11 }}>{row.vehicle}</td>
                <td style={{ padding: '8px 10px', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>{row.price}</td>
                <td style={{ padding: '8px 10px' }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                    <span style={{
                      flexShrink: 0, fontSize: 9, fontWeight: 700, letterSpacing: '0.06em',
                      padding: '2px 6px', borderRadius: 4,
                      color: urg.color, background: urg.bg,
                    }}>{urg.label}</span>
                    <span style={{ color: 'var(--text-primary)', fontSize: 11, lineHeight: 1.4 }}>{row.action}</span>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function CategoryCard({ cat }: { cat: typeof CATEGORIES[0] }) {
  return (
    <div style={{
      background: '#11161f',
      borderLeft: `3px solid ${cat.color}`,
      borderRadius: 6,
      padding: '14px 16px',
      display: 'flex',
      flexDirection: 'column',
      gap: 10,
    }}>
      {/* Header */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <span style={{ fontSize: 15 }}>{cat.icon}</span>
          <span style={{ fontSize: 13, fontWeight: 700, color: cat.color }}>{cat.title}</span>
        </div>
        <p style={{ fontSize: 11, color: 'var(--text-tertiary)', lineHeight: 1.5, margin: 0 }}>{cat.desc}</p>
      </div>

      {/* Table */}
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${cat.color}40` }}>
            {['Item', 'Status', 'Pri', 'Notes'].map(h => (
              <th key={h} style={{ padding: '4px 6px', textAlign: 'left', fontSize: 9, fontWeight: 700, color: 'var(--text-tertiary)', letterSpacing: '0.04em', background: 'var(--surface-alt)' }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {cat.items.map((item, i) => (
            <tr key={i} style={{ background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)', borderBottom: '1px solid var(--border-light)' }}>
              <td style={{ padding: '5px 6px', color: 'var(--text-primary)', lineHeight: 1.4 }}>{item.label}</td>
              <td style={{ padding: '5px 6px', color: item.statusColor, fontWeight: 600, whiteSpace: 'nowrap' }}>{item.status}</td>
              <td style={{ padding: '5px 6px', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>{item.priority}</td>
              <td style={{ padding: '5px 6px', color: 'var(--text-tertiary)' }}>{item.note}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Footer */}
      {cat.footer && (
        <div style={{ paddingTop: 6, borderTop: '1px solid var(--border-light)' }}>
          <span style={{ fontSize: 9, fontWeight: 700, color: 'var(--accent)', letterSpacing: '0.04em' }}>REVENUE MODEL  </span>
          <span style={{ fontSize: 10, color: 'var(--text-secondary)' }}>{cat.footer}</span>
        </div>
      )}
    </div>
  );
}

function TerminalDashboard() {
  return (
    <div style={{ background: '#0a0d12', borderRadius: 8, overflow: 'hidden', border: '1px solid var(--border)' }}>
      {/* Chrome */}
      <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#ff5f56', display: 'inline-block' }} />
        <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#ffbd2e', display: 'inline-block' }} />
        <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#27c93f', display: 'inline-block' }} />
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-tertiary)', marginLeft: 8 }}>
          ~/eva/portfolio.sh
        </span>
      </div>

      {/* Table */}
      <div style={{ padding: '12px 0' }}>
        <div style={{ padding: '0 14px 8px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--accent)' }}>
          $ portfolio --status
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              {['CATEGORY', 'CASH NOW?', 'STAGE', 'JUNE 25 CONTRIBUTION'].map(h => (
                <th key={h} style={{ padding: '6px 14px', textAlign: 'left', fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 700, letterSpacing: '0.05em' }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {DASHBOARD_ROWS.map((row, i) => (
              <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                <td style={{ padding: '7px 14px', color: 'var(--text-primary)' }}>{row.cat}</td>
                <td style={{ padding: '7px 14px', color: row.cashColor, fontWeight: 700 }}>{row.cashNow}</td>
                <td style={{ padding: '7px 14px', color: 'var(--text-tertiary)' }}>{row.stage}</td>
                <td style={{ padding: '7px 14px', color: 'var(--text-primary)' }}>{row.contribution}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{ padding: '10px 14px 4px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--accent)' }}>
          $ <span style={{ opacity: 0.5, animation: 'pulse 1.2s infinite' }}>_</span>
        </div>
      </div>
    </div>
  );
}

function OneThingTable() {
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
      <thead>
        <tr style={{ borderBottom: '1.5px solid #ff9500' }}>
          {['CATEGORY', 'ONE ACTION', 'DO IT BY'].map(h => (
            <th key={h} style={{ padding: '7px 12px', textAlign: 'left', fontSize: 10, fontWeight: 700, color: 'var(--text-secondary)', letterSpacing: '0.04em', background: 'var(--surface-alt)' }}>
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {ONE_THING_ROWS.map((row, i) => (
          <tr key={i} style={{ background: i % 2 === 0 ? 'var(--surface)' : '#1a2030', borderLeft: `3px solid ${row.color}` }}>
            <td style={{ padding: '10px 12px', color: 'var(--text-primary)', fontWeight: 700 }}>{row.cat}</td>
            <td style={{ padding: '10px 12px', color: 'var(--text-primary)' }}>{row.action}</td>
            <td style={{ padding: '10px 12px', color: row.color, fontWeight: 700, whiteSpace: 'nowrap', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
              {row.when}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ─────────────────────────────────────────
   TAB LAYOUT
───────────────────────────────────────── */
type Tab = 'revenue' | 'projects' | 'dashboard';
const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: 'revenue',   label: 'Revenue Streams', icon: '💰' },
  { id: 'projects',  label: 'Project Portfolio', icon: '📁' },
  { id: 'dashboard', label: 'Portfolio Dashboard', icon: '⚡' },
];

/* ─────────────────────────────────────────
   MAIN EXPORT
───────────────────────────────────────── */
export function PortfolioMap() {
  const [activeTab, setActiveTab] = useState<Tab>('revenue');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* North Star Banner */}
      <div style={{
        background: 'linear-gradient(135deg, rgba(0,192,127,0.08) 0%, rgba(0,192,127,0.03) 100%)',
        border: '1px solid rgba(0,192,127,0.25)',
        borderRadius: 8,
        padding: '12px 18px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 10,
      }}>
        <div>
          <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--accent)', letterSpacing: '0.06em' }}>NORTH STAR</span>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', marginTop: 2 }}>
            $10K net/month · Deal closed · June 25, 2026
          </div>
        </div>
        <div style={{ display: 'flex', gap: 16 }}>
          {[
            { label: 'Frame', value: 'ONE MAN ARMY', color: 'var(--accent)' },
            { label: 'Capital', value: '$200K HELOC', color: '#4d9fff' },
            { label: 'Streams', value: '15 identified', color: '#ff9500' },
            { label: 'Projects', value: '6 categories', color: 'var(--accent)' },
          ].map(kpi => (
            <div key={kpi.label} style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 10, color: 'var(--text-tertiary)', letterSpacing: '0.04em' }}>{kpi.label}</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: kpi.color }}>{kpi.value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, borderBottom: '1px solid var(--border)' }}>
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: '8px 16px',
              fontSize: 12,
              fontWeight: 600,
              border: 'none',
              borderBottom: activeTab === tab.id ? '2px solid var(--accent)' : '2px solid transparent',
              background: 'transparent',
              color: activeTab === tab.id ? 'var(--text-primary)' : 'var(--text-tertiary)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              transition: 'color 0.15s',
              marginBottom: -1,
            }}
          >
            <span>{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Revenue Streams Tab ── */}
      {activeTab === 'revenue' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div style={{
            background: 'var(--surface)',
            borderLeft: '3px solid var(--accent)',
            borderRadius: 4,
            padding: '10px 14px',
            fontSize: 12,
            color: 'var(--text-secondary)',
          }}>
            What can generate cash <strong style={{ color: 'var(--text-primary)' }}>now</strong>.
            Tier 1 acts today, Tier 2 builds underway, Tier 3 infrastructure phase.
          </div>

          {REVENUE_TIERS.map(tier => (
            <div key={tier.tier}>
              <TierBadge label={tier.label} sublabel={tier.sublabel} note={tier.note} color={tier.color} />
              <RevenueTable rows={tier.rows} accentColor={tier.color} tierNum={tier.tier} />
            </div>
          ))}
        </div>
      )}

      {/* ── Project Portfolio Tab ── */}
      {activeTab === 'projects' && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(480px, 1fr))',
          gap: 16,
        }}>
          {CATEGORIES.map(cat => (
            <CategoryCard key={cat.key} cat={cat} />
          ))}
        </div>
      )}

      {/* ── Portfolio Dashboard Tab ── */}
      {activeTab === 'dashboard' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <TerminalDashboard />

          <div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 12 }}>
              <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>
                The ONE THING Each Category Needs Right Now
              </span>
              <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>— Action items · Time-bound</span>
            </div>
            <OneThingTable />
          </div>

          {/* Summary stats */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginTop: 4 }}>
            {[
              { label: 'P1 Actions Today', value: '6', color: '#ff3b30' },
              { label: 'Revenue Streams', value: '15', color: 'var(--accent)' },
              { label: 'Active Deals', value: '3', color: '#4d9fff' },
              { label: 'Days to North Star', value: '30', color: '#ff9500' },
            ].map(stat => (
              <div key={stat.label} style={{
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: 6,
                padding: '14px 16px',
                textAlign: 'center',
              }}>
                <div style={{ fontSize: 28, fontWeight: 700, color: stat.color, fontFamily: 'var(--font-mono)' }}>
                  {stat.value}
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 4, letterSpacing: '0.03em' }}>
                  {stat.label}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

    </div>
  );
}
