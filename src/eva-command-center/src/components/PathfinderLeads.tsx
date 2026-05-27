/**
 * PathfinderLeads — Incubator pipeline panel
 * Fetches from GET /pathfinder/leads (port 8773)
 * Shows: name, email, tier, score, stage, follow-up badge
 */

import { useEffect, useState, useCallback } from 'react';

const PATHFINDER_URL = 'http://localhost:8773';
const VERCEL_LEADS_URL = 'https://eva-waitlist.vercel.app/api/leads';
const LEADS_SECRET = (import.meta as unknown as { env: Record<string, string> }).env?.VITE_LEADS_SECRET || '';

type Stage = 'new' | 'contacted' | 'replied' | 'meeting_booked' | 'closed' | 'archived';

interface Lead {
  id: number;
  name: string;
  email: string;
  company?: string;
  tier: string;
  usecase?: string;
  score: number;
  sequence: string;
  stage: Stage;
  created_at: string;
  last_contact?: string;
  notes?: string;
}

interface LeadsResponse {
  total: number;
  follow_up_today: number;
  leads: Lead[];
}

const STAGE_LABELS: Record<Stage, string> = {
  new:            'New',
  contacted:      'Contacted',
  replied:        'Replied',
  meeting_booked: 'Meeting',
  closed:         'Closed',
  archived:       'Archived',
};

const STAGE_COLORS: Record<Stage, { bg: string; color: string }> = {
  new:            { bg: '#EFF6FF', color: '#2563EB' },
  contacted:      { bg: '#FFF7ED', color: '#EA580C' },
  replied:        { bg: '#F0FDF4', color: '#16A34A' },
  meeting_booked: { bg: '#FAF5FF', color: '#7C3AED' },
  closed:         { bg: '#ECFDF5', color: '#00C07F' },
  archived:       { bg: '#F9FAFB', color: '#9CA3AF' },
};

const TIER_COLORS: Record<string, string> = {
  enterprise: '#7C3AED',
  operator:   '#00C07F',
  starter:    '#2563EB',
  unsure:     '#9CA3AF',
};

function ScoreBar({ score }: { score: number }) {
  const color = score >= 80 ? '#00C07F' : score >= 60 ? '#F59E0B' : '#9CA3AF';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{
        width: 48, height: 4, borderRadius: 2,
        background: '#F3F4F6', overflow: 'hidden',
      }}>
        <div style={{ width: `${score}%`, height: '100%', background: color, borderRadius: 2 }} />
      </div>
      <span style={{ fontSize: 11, fontWeight: 600, color, minWidth: 22 }}>{score}</span>
    </div>
  );
}

function EmptyState({ offline }: { offline: boolean }) {
  return (
    <div style={{
      textAlign: 'center', padding: '40px 20px',
      color: 'var(--text-tertiary)',
    }}>
      {offline ? (
        <>
          <div style={{ fontSize: 28, marginBottom: 8 }}>⚡</div>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>
            Pathfinder offline
          </div>
          <div style={{ fontSize: 12 }}>
            Run <code style={{ background: '#F3F4F6', padding: '1px 5px', borderRadius: 3, fontSize: 11 }}>
              python pathfinder_api.py
            </code> on your Mac to activate.
          </div>
        </>
      ) : (
        <>
          <div style={{ fontSize: 28, marginBottom: 8 }}>🌱</div>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>
            No leads yet
          </div>
          <div style={{ fontSize: 12 }}>Waitlist submissions will appear here.</div>
        </>
      )}
    </div>
  );
}

export function PathfinderLeads() {
  const [data, setData] = useState<LeadsResponse | null>(null);
  const [offline, setOffline] = useState(false);
  const [loading, setLoading] = useState(true);
  const [advancing, setAdvancing] = useState<number | null>(null);

  const fetchLeads = useCallback(async () => {
    // Try local Pathfinder first
    try {
      const res = await fetch(`${PATHFINDER_URL}/pathfinder/leads`, {
        signal: AbortSignal.timeout(3000),
      });
      if (!res.ok) throw new Error('not ok');
      const json: LeadsResponse = await res.json();
      setData(json);
      setOffline(false);
      setLoading(false);
      return;
    } catch { /* fall through to Vercel */ }

    // Fallback: Vercel /api/leads (Neon Postgres — always live)
    try {
      const headers: Record<string, string> = {};
      if (LEADS_SECRET) headers['Authorization'] = `Bearer ${LEADS_SECRET}`;
      const res = await fetch(VERCEL_LEADS_URL, {
        headers,
        signal: AbortSignal.timeout(5000),
      });
      if (!res.ok) throw new Error('not ok');
      const json: LeadsResponse = await res.json();
      setData(json);
      setOffline(false);
    } catch {
      setOffline(true);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLeads();
    const id = setInterval(fetchLeads, 30000);
    return () => clearInterval(id);
  }, [fetchLeads]);

  const advanceLead = async (id: number) => {
    setAdvancing(id);
    try {
      await fetch(`${PATHFINDER_URL}/pathfinder/lead/${id}/advance`, {
        method: 'POST',
        signal: AbortSignal.timeout(3000),
      });
      await fetchLeads();
    } catch {
      // silent — offline
    } finally {
      setAdvancing(null);
    }
  };

  const followUpCount = data?.follow_up_today ?? 0;
  const leads = data?.leads ?? [];
  const activeLeads = leads.filter(l => l.stage !== 'archived');

  return (
    <div className="eva-card" style={{ padding: 0, overflow: 'hidden' }}>
      {/* Header */}
      <div style={{
        padding: '16px 20px',
        borderBottom: '1px solid var(--border-light)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 16 }}>🌱</span>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
              Pathfinder Pipeline
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 1 }}>
              Waitlist leads · scored · sequenced
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {followUpCount > 0 && (
            <span style={{
              background: '#FEF3C7', color: '#B45309',
              fontSize: 10, fontWeight: 700, padding: '2px 8px',
              borderRadius: 10, letterSpacing: '0.03em',
            }}>
              {followUpCount} FOLLOW UP TODAY
            </span>
          )}
          {data && (
            <span style={{
              background: 'var(--bg-secondary)', color: 'var(--text-tertiary)',
              fontSize: 10, padding: '2px 7px', borderRadius: 6,
              fontWeight: 600,
            }}>
              {data.total} total
            </span>
          )}
          <div style={{
            width: 7, height: 7, borderRadius: '50%',
            background: offline ? '#EF4444' : '#00C07F',
          }} />
          <button
            onClick={fetchLeads}
            style={{
              fontSize: 11, color: 'var(--text-tertiary)',
              background: 'none', border: 'none', cursor: 'pointer', padding: '2px 6px',
            }}
          >
            ↻
          </button>
        </div>
      </div>

      {/* Body */}
      {loading ? (
        <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 12 }}>
          Loading leads…
        </div>
      ) : (offline || activeLeads.length === 0) ? (
        <EmptyState offline={offline} />
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ background: 'var(--bg-secondary)' }}>
                {['Name', 'Tier', 'Score', 'Stage', 'Use Case', 'Joined', ''].map(h => (
                  <th key={h} style={{
                    padding: '8px 14px', textAlign: 'left',
                    fontSize: 10, fontWeight: 600, color: 'var(--text-tertiary)',
                    letterSpacing: '0.05em', textTransform: 'uppercase',
                    borderBottom: '1px solid var(--border-light)',
                    whiteSpace: 'nowrap',
                  }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {activeLeads.map((lead, i) => {
                const stageStyle = STAGE_COLORS[lead.stage] ?? { bg: '#F9FAFB', color: '#6B7280' };
                const tierColor = TIER_COLORS[lead.tier] ?? '#9CA3AF';
                const isFollowUp = (lead.stage === 'new' || lead.stage === 'contacted') &&
                  (!lead.last_contact || lead.last_contact < new Date().toISOString().slice(0, 10));

                return (
                  <tr
                    key={lead.id}
                    style={{
                      borderBottom: i < activeLeads.length - 1 ? '1px solid var(--border-light)' : 'none',
                      background: isFollowUp ? '#FFFBEB' : 'transparent',
                    }}
                  >
                    {/* Name */}
                    <td style={{ padding: '10px 14px' }}>
                      <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{lead.name}</div>
                      <div style={{ color: 'var(--text-tertiary)', fontSize: 11 }}>{lead.email}</div>
                      {lead.company && (
                        <div style={{ color: 'var(--text-tertiary)', fontSize: 10, marginTop: 1 }}>
                          {lead.company}
                        </div>
                      )}
                    </td>

                    {/* Tier */}
                    <td style={{ padding: '10px 14px' }}>
                      <span style={{
                        fontSize: 10, fontWeight: 700, padding: '2px 7px',
                        borderRadius: 8, background: `${tierColor}18`, color: tierColor,
                        textTransform: 'capitalize', letterSpacing: '0.02em',
                      }}>
                        {lead.tier}
                      </span>
                    </td>

                    {/* Score */}
                    <td style={{ padding: '10px 14px' }}>
                      <ScoreBar score={lead.score} />
                    </td>

                    {/* Stage */}
                    <td style={{ padding: '10px 14px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                        <span style={{
                          fontSize: 10, fontWeight: 600, padding: '2px 8px',
                          borderRadius: 8, background: stageStyle.bg, color: stageStyle.color,
                          whiteSpace: 'nowrap',
                        }}>
                          {STAGE_LABELS[lead.stage]}
                        </span>
                        {isFollowUp && (
                          <span style={{
                            fontSize: 9, fontWeight: 700, color: '#B45309',
                            background: '#FEF3C7', padding: '1px 5px', borderRadius: 4,
                          }}>
                            TODAY
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Use Case */}
                    <td style={{ padding: '10px 14px', maxWidth: 180 }}>
                      <span style={{
                        color: 'var(--text-secondary)', fontSize: 11,
                        display: '-webkit-box', WebkitLineClamp: 2,
                        WebkitBoxOrient: 'vertical', overflow: 'hidden',
                      }}>
                        {lead.usecase ?? '—'}
                      </span>
                    </td>

                    {/* Joined */}
                    <td style={{ padding: '10px 14px', whiteSpace: 'nowrap' }}>
                      <span style={{ color: 'var(--text-tertiary)', fontSize: 11 }}>
                        {new Date(lead.created_at).toLocaleDateString('en-US', {
                          month: 'short', day: 'numeric',
                        })}
                      </span>
                    </td>

                    {/* Advance */}
                    <td style={{ padding: '10px 14px' }}>
                      {lead.stage !== 'closed' && lead.stage !== 'archived' && (
                        <button
                          onClick={() => advanceLead(lead.id)}
                          disabled={advancing === lead.id}
                          style={{
                            fontSize: 10, fontWeight: 600,
                            padding: '3px 9px', borderRadius: 6,
                            background: 'var(--bg-secondary)',
                            border: '1px solid var(--border)',
                            color: 'var(--text-secondary)',
                            cursor: advancing === lead.id ? 'default' : 'pointer',
                            opacity: advancing === lead.id ? 0.5 : 1,
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {advancing === lead.id ? '…' : 'Advance →'}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
