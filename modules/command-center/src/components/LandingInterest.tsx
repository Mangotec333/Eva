import { useEffect, useState, useCallback } from 'react';

/* ─────────────────────────────────────────
   TYPES
───────────────────────────────────────── */
interface LandingPage {
  name: string;
  path: string;
  url: string;
  live: boolean;
  status: number | null;
  error: string | null;
}

interface Magnet {
  label: string;
  tag: string;
  count: number | null;
  ok: boolean;
}

interface LandingReport {
  available?: boolean;
  reason?: string;
  generated_at?: string;
  ghl_offline?: boolean;
  landing: LandingPage[];
  magnets: Magnet[];
  total: { tag: string; count: number | null; ok: boolean };
  summary?: { pages_live: number; pages_total: number; total_leads: number | null };
}

/* ─────────────────────────────────────────
   DATA
───────────────────────────────────────── */
const EMPTY: LandingReport = {
  landing: [],
  magnets: [],
  total: { tag: 'eva-acquisition-lead', count: null, ok: false },
};

async function fetchLanding(): Promise<LandingReport> {
  try {
    const res = await fetch('http://localhost:8768/landing_status', {
      signal: AbortSignal.timeout(4000),
    });
    if (res.ok) {
      const data = (await res.json()) as LandingReport;
      if (data.available !== false && Array.isArray(data.landing)) return data;
    }
  } catch {}
  return EMPTY;
}

function countStr(n: number | null | undefined): string {
  return n === null || n === undefined ? '—' : String(n);
}

/* ─────────────────────────────────────────
   PANEL
───────────────────────────────────────── */
export function LandingInterest() {
  const [report, setReport] = useState<LandingReport>(EMPTY);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    fetchLanding().then((d) => {
      setReport(d);
      setLoading(false);
    });
  }, []);

  useEffect(() => { load(); }, [load]);

  const pagesLive = report.summary?.pages_live ?? report.landing.filter((p) => p.live).length;
  const pagesTotal = report.summary?.pages_total ?? report.landing.length;

  return (
    <div style={{ background: '#111111', border: '1px solid #1e1e1e', borderRadius: 12, padding: 16 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', color: '#06b6d4', textTransform: 'uppercase' }}>
          Landing + Interest
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {report.ghl_offline && (
            <span style={{ fontSize: 9, color: '#f59e0b', fontFamily: 'ui-monospace, monospace' }}>GHL OFFLINE</span>
          )}
          <span style={{ fontSize: 10, color: '#4b5563', fontFamily: 'ui-monospace, monospace' }}>
            {pagesLive}/{pagesTotal || 0} live
          </span>
          <button
            onClick={load}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#4b5563', fontSize: 11, fontFamily: 'ui-monospace, monospace' }}
            title="Refresh"
          >
            ↺
          </button>
        </div>
      </div>

      {loading && report.landing.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '18px 0', color: '#4b5563', fontSize: 12, fontFamily: 'ui-monospace, monospace' }}>
          Loading…
        </div>
      ) : report.landing.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '18px 0', color: '#6b7280', fontSize: 12, fontFamily: 'ui-monospace, monospace' }}>
          {report.reason ?? 'Tracker has not run yet — run eva-landing-status.sh'}
        </div>
      ) : (
        <>
          {/* Landing pages */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 14 }}>
            {report.landing.map((p) => (
              <div key={p.path} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{
                  width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                  background: p.live ? '#22c55e' : '#ef4444',
                  boxShadow: p.live ? '0 0 6px rgba(34,197,94,0.5)' : '0 0 6px rgba(239,68,68,0.4)',
                }} />
                <span style={{ fontSize: 12, color: p.live ? '#e5e7eb' : '#9ca3af', flex: 1 }}>{p.name}</span>
                <span style={{ fontSize: 10, color: '#4b5563', fontFamily: 'ui-monospace, monospace' }}>
                  {p.live ? (p.status ?? 'OK') : (p.status ?? 'DOWN')}
                </span>
              </div>
            ))}
          </div>

          {/* Magnet interest */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
            {report.magnets.map((m) => (
              <div key={m.tag} style={{
                background: '#0a0a0a', border: '1px solid #1e1e1e', borderRadius: 8, padding: '8px 10px',
              }}>
                <div style={{ fontSize: 10, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{m.label}</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: '#ffffff', fontFamily: 'ui-monospace, monospace' }}>
                  {countStr(m.count)}
                </div>
              </div>
            ))}
          </div>

          {/* Total */}
          <div style={{
            marginTop: 12, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            paddingTop: 12, borderTop: '1px solid #1a1a1a',
          }}>
            <span style={{ fontSize: 11, color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Total leads
            </span>
            <span style={{ fontSize: 20, fontWeight: 700, color: '#22c55e', fontFamily: 'ui-monospace, monospace' }}>
              {countStr(report.total.count)}
            </span>
          </div>
        </>
      )}
    </div>
  );
}

export default LandingInterest;
