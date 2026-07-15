import { useState, useEffect, useCallback } from 'react';
import { Globe, RefreshCw } from 'lucide-react';

// ─── Types ──────────────────────────────────────────────────────────────────

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

// ─── Component ────────────────────────────────────────────────────────────────

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
    <div className="bg-[#111] border border-[#1a1a1a] rounded-lg p-4 flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Globe className="w-4 h-4 text-[#00ff88]" />
          <span className="font-mono text-xs font-bold text-gray-400 tracking-widest uppercase">
            Landing + Interest
          </span>
        </div>
        <div className="flex items-center gap-3">
          {report.ghl_offline && (
            <span className="font-mono text-[9px] font-bold text-amber-400 tracking-widest uppercase">
              GHL Offline
            </span>
          )}
          <span className="font-mono text-[10px] text-gray-500">
            {pagesLive}/{pagesTotal || 0} live
          </span>
          <button
            onClick={load}
            className="p-1 text-gray-600 hover:text-[#00ff88] transition-colors"
            title="Refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {loading && report.landing.length === 0 ? (
        <div className="py-6 text-center font-mono text-xs text-gray-600 animate-pulse">Loading…</div>
      ) : report.landing.length === 0 ? (
        <div className="py-6 text-center font-mono text-xs text-gray-600">
          {report.reason ?? 'Tracker has not run yet — run eva-landing-status.sh'}
        </div>
      ) : (
        <>
          {/* Landing pages */}
          <div className="flex flex-col gap-1.5">
            {report.landing.map((p) => (
              <div key={p.path} className="flex items-center gap-2.5">
                <span
                  className={`w-1.5 h-1.5 rounded-full shrink-0 ${p.live ? 'bg-[#00ff88]' : 'bg-red-500'}`}
                />
                <span className={`font-mono text-xs flex-1 ${p.live ? 'text-gray-300' : 'text-gray-500'}`}>
                  {p.name}
                </span>
                <span className="font-mono text-[10px] text-gray-600">
                  {p.live ? (p.status ?? 'OK') : (p.status ?? 'DOWN')}
                </span>
              </div>
            ))}
          </div>

          {/* Magnet interest */}
          <div className="grid grid-cols-2 gap-2 mt-1">
            {report.magnets.map((m) => (
              <div key={m.tag} className="bg-[#0a0a0a] border border-[#1a1a1a] rounded px-3 py-2">
                <div className="font-mono text-[10px] text-gray-500 uppercase tracking-widest">{m.label}</div>
                <div className="font-mono text-lg font-bold text-gray-100 tabular-nums">{countStr(m.count)}</div>
              </div>
            ))}
          </div>

          {/* Total */}
          <div className="flex items-center justify-between pt-2 border-t border-[#1a1a1a]">
            <span className="font-mono text-[10px] text-gray-500 uppercase tracking-widest">Total leads</span>
            <span className="font-mono text-xl font-bold text-[#00ff88] tabular-nums">{countStr(report.total.count)}</span>
          </div>
        </>
      )}
    </div>
  );
}

export default LandingInterest;
