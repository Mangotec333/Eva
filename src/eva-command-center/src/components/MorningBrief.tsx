import { useEffect, useState } from 'react';

interface CalendarEvent {
  title: string;
  start_time: string;
  end_time?: string;
  attendees?: string[];
  zoom_link?: string;
  is_high_stakes?: boolean;
}

interface DealSignal {
  subject: string;
  sender: string;
  signal_type: string;
  summary: string;
}

interface NapBlock {
  before_event: string;
  start_time: string;
  end_time: string;
  reason: string;
}

interface MorningBriefData {
  date: string;
  generated_at: string;
  calendar: CalendarEvent[];
  deal_signals: DealSignal[];
  actions: string[];
  nap_blocks: NapBlock[];
  exercise_block?: { time: string; duration: string };
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
      timeZone: 'America/Los_Angeles',
    });
  } catch {
    return iso;
  }
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('en-US', {
      weekday: 'long',
      month: 'long',
      day: 'numeric',
      timeZone: 'America/Los_Angeles',
    });
  } catch {
    return iso;
  }
}

const SIGNAL_COLORS: Record<string, { bg: string; text: string; dot: string }> = {
  deal_flow:   { bg: '#f0fdf4', text: '#166534', dot: '#22c55e' },
  meeting:     { bg: '#eff6ff', text: '#1e40af', dot: '#3b82f6' },
  follow_up:   { bg: '#fefce8', text: '#854d0e', dot: '#eab308' },
  newsletter:  { bg: '#f9fafb', text: '#374151', dot: '#9ca3af' },
};

// Load from local JSON file served by EVA backend, fallback to mock
async function fetchBrief(): Promise<MorningBriefData | null> {
  try {
    const res = await fetch('http://localhost:8768/morning_brief', {
      signal: AbortSignal.timeout(2000),
    });
    if (res.ok) return res.json();
  } catch {}

  // Fallback: mock data so UI always renders
  const today = new Date().toISOString();
  return {
    date: today,
    generated_at: today,
    exercise_block: { time: '7:15 AM', duration: '45 min' },
    nap_blocks: [],
    calendar: [],
    deal_signals: [],
    actions: ['Run EVA email agent to populate live data'],
  };
}

export function MorningBrief() {
  const [brief, setBrief] = useState<MorningBriefData | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(true);

  useEffect(() => {
    fetchBrief().then((data) => {
      setBrief(data);
      setLoading(false);
    });
  }, []);

  const today = brief?.date ? formatDate(brief.date) : formatDate(new Date().toISOString());

  return (
    <div
      className="rounded-xl border overflow-hidden"
      style={{ background: '#fff', borderColor: '#e5e7eb' }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 border-b cursor-pointer select-none"
        style={{ borderColor: '#e5e7eb', background: '#f9fafb' }}
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex items-center gap-3">
          <span style={{ fontSize: 18 }}>☀️</span>
          <div>
            <div className="font-semibold text-gray-800 text-sm">Morning Brief</div>
            <div className="text-xs text-gray-400 font-mono">{today}</div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {brief && (
            <span className="text-xs text-gray-400 font-mono">
              {brief.calendar.length} events · {brief.deal_signals.length} signals
            </span>
          )}
          <span className="text-gray-400 text-xs">{expanded ? '▲' : '▼'}</span>
        </div>
      </div>

      {expanded && (
        <div className="p-4 space-y-4">
          {loading && (
            <div className="text-center py-6 text-gray-400 text-sm font-mono animate-pulse">
              Loading brief...
            </div>
          )}

          {!loading && brief && (
            <>
              {/* ── Protected Blocks ─────────────────── */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {/* Exercise block */}
                <div
                  className="flex items-center gap-3 rounded-lg px-3 py-2.5"
                  style={{ background: '#f0fdf4', border: '1px solid #bbf7d0' }}
                >
                  <span style={{ fontSize: 20 }}>🏃</span>
                  <div>
                    <div className="text-xs font-semibold text-green-800">Exercise Block</div>
                    <div className="text-xs text-green-700 font-mono">
                      {brief.exercise_block?.time ?? '7:15 AM'} · {brief.exercise_block?.duration ?? '45 min'} · Protected
                    </div>
                  </div>
                </div>

                {/* Nap protocol */}
                {brief.nap_blocks.length > 0 ? (
                  brief.nap_blocks.map((nap, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-3 rounded-lg px-3 py-2.5"
                      style={{ background: '#faf5ff', border: '1px solid #e9d5ff' }}
                    >
                      <span style={{ fontSize: 20 }}>💤</span>
                      <div>
                        <div className="text-xs font-semibold text-purple-800">
                          Pre-Call Nap · {nap.before_event}
                        </div>
                        <div className="text-xs text-purple-700 font-mono">
                          {formatTime(nap.start_time)} – {formatTime(nap.end_time)} · Diffuse window
                        </div>
                      </div>
                    </div>
                  ))
                ) : (
                  <div
                    className="flex items-center gap-3 rounded-lg px-3 py-2.5"
                    style={{ background: '#faf5ff', border: '1px dashed #e9d5ff' }}
                  >
                    <span style={{ fontSize: 20 }}>💤</span>
                    <div>
                      <div className="text-xs font-semibold text-purple-600">Nap Protocol</div>
                      <div className="text-xs text-purple-400 font-mono">
                        No high-stakes calls today
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* ── Calendar ─────────────────────────── */}
              {brief.calendar.length > 0 && (
                <div>
                  <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                    Today's Calendar
                  </div>
                  <div className="space-y-1.5">
                    {brief.calendar.map((evt, i) => (
                      <div
                        key={i}
                        className="flex items-start gap-3 rounded-lg px-3 py-2"
                        style={{
                          background: evt.is_high_stakes ? '#fff7ed' : '#f9fafb',
                          border: `1px solid ${evt.is_high_stakes ? '#fed7aa' : '#e5e7eb'}`,
                        }}
                      >
                        <span style={{ fontSize: 15, marginTop: 1 }}>
                          {evt.is_high_stakes ? '🔴' : '📅'}
                        </span>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-medium text-gray-800 truncate">
                              {evt.title}
                            </span>
                            {evt.is_high_stakes && (
                              <span
                                className="text-xs px-1.5 py-0.5 rounded font-mono"
                                style={{ background: '#fed7aa', color: '#9a3412' }}
                              >
                                HIGH STAKES
                              </span>
                            )}
                          </div>
                          <div className="text-xs text-gray-500 font-mono mt-0.5">
                            {formatTime(evt.start_time)}
                            {evt.end_time && ` – ${formatTime(evt.end_time)}`}
                            {evt.attendees && evt.attendees.length > 0 &&
                              ` · ${evt.attendees.slice(0, 2).join(', ')}${evt.attendees.length > 2 ? ` +${evt.attendees.length - 2}` : ''}`
                            }
                          </div>
                          {evt.zoom_link && (
                            <a
                              href={evt.zoom_link}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs text-blue-500 hover:underline font-mono mt-0.5 inline-block"
                            >
                              Join Zoom →
                            </a>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* ── Deal Signals ──────────────────────── */}
              {brief.deal_signals.length > 0 && (
                <div>
                  <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                    Deal Signals from Inbox
                  </div>
                  <div className="space-y-1.5">
                    {brief.deal_signals.map((sig, i) => {
                      const colors = SIGNAL_COLORS[sig.signal_type] ?? SIGNAL_COLORS.newsletter;
                      return (
                        <div
                          key={i}
                          className="flex items-start gap-2.5 rounded-lg px-3 py-2"
                          style={{ background: colors.bg, border: `1px solid ${colors.dot}33` }}
                        >
                          <span
                            className="rounded-full shrink-0 mt-1.5"
                            style={{ width: 7, height: 7, background: colors.dot }}
                          />
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium truncate" style={{ color: colors.text }}>
                              {sig.subject}
                            </div>
                            <div className="text-xs mt-0.5" style={{ color: colors.text, opacity: 0.7 }}>
                              {sig.sender} · {sig.signal_type.replace('_', ' ')}
                            </div>
                            {sig.summary && (
                              <div className="text-xs mt-1 text-gray-600 line-clamp-2">
                                {sig.summary}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* ── Action Queue ──────────────────────── */}
              {brief.actions.length > 0 && (
                <div>
                  <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                    Actions
                  </div>
                  <div className="space-y-1">
                    {brief.actions.map((action, i) => (
                      <div key={i} className="flex items-start gap-2 text-sm text-gray-700">
                        <span className="text-gray-400 shrink-0 mt-0.5">→</span>
                        <span>{action}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Empty state */}
              {brief.calendar.length === 0 && brief.deal_signals.length === 0 && (
                <div
                  className="text-center py-4 rounded-lg text-sm text-gray-500 font-mono"
                  style={{ background: '#f9fafb', border: '1px dashed #e5e7eb' }}
                >
                  Email agent hasn't run yet — cron fires at 7am daily
                </div>
              )}

              {/* Footer */}
              <div className="flex items-center justify-between pt-1">
                <div className="text-xs text-gray-400 font-mono">
                  {brief.generated_at
                    ? `Generated ${formatTime(brief.generated_at)}`
                    : 'Not yet generated'}
                </div>
                <button
                  onClick={() => { setLoading(true); fetchBrief().then(d => { setBrief(d); setLoading(false); }); }}
                  className="text-xs text-gray-400 hover:text-gray-600 font-mono transition-colors"
                >
                  ↺ refresh
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
