/**
 * WellnessBlocks — Exercise Block + Nap Protocol
 * Lives under Personal > My Day
 */

import { useEffect, useState } from 'react';

interface NapBlock {
  before_event: string;
  start_time: string;
  end_time: string;
  reason: string;
}

interface WellnessData {
  exercise_block?: { time: string; duration: string };
  nap_blocks: NapBlock[];
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

async function fetchWellness(): Promise<WellnessData> {
  try {
    const res = await fetch('http://localhost:8768/morning_brief', {
      signal: AbortSignal.timeout(2000),
    });
    if (res.ok) {
      const data = await res.json();
      return { exercise_block: data.exercise_block, nap_blocks: data.nap_blocks ?? [] };
    }
  } catch {}
  // Fallback
  return { exercise_block: { time: '7:15 AM', duration: '45 min' }, nap_blocks: [] };
}

export function WellnessBlocks() {
  const [data, setData] = useState<WellnessData>({
    exercise_block: { time: '7:15 AM', duration: '45 min' },
    nap_blocks: [],
  });

  useEffect(() => {
    fetchWellness().then(setData);
  }, []);

  return (
    <div
      className="rounded-xl border overflow-hidden"
      style={{ background: '#fff', borderColor: '#e5e7eb' }}
    >
      {/* Header */}
      <div
        className="flex items-center gap-3 px-4 py-3 border-b"
        style={{ borderColor: '#e5e7eb', background: '#f9fafb' }}
      >
        <span style={{ fontSize: 17 }}>🧬</span>
        <div>
          <div className="font-semibold text-gray-800 text-sm">Body Protocol</div>
          <div className="text-xs text-gray-400 font-mono">Exercise · Recovery · Energy</div>
        </div>
      </div>

      <div className="p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">

          {/* Exercise Block */}
          <div
            className="flex items-start gap-3 rounded-lg px-4 py-3"
            style={{ background: '#f0fdf4', border: '1px solid #bbf7d0' }}
          >
            <span style={{ fontSize: 22, lineHeight: 1.2 }}>🏃</span>
            <div>
              <div className="text-xs font-bold text-green-800 uppercase tracking-wide mb-1">
                Exercise Block
              </div>
              <div className="text-sm font-semibold text-green-900">
                {data.exercise_block?.time ?? '7:15 AM'}
              </div>
              <div className="text-xs text-green-700 font-mono mt-0.5">
                {data.exercise_block?.duration ?? '45 min'} · Protected
              </div>
            </div>
          </div>

          {/* Nap Protocol */}
          {data.nap_blocks.length > 0 ? (
            data.nap_blocks.map((nap, i) => (
              <div
                key={i}
                className="flex items-start gap-3 rounded-lg px-4 py-3"
                style={{ background: '#faf5ff', border: '1px solid #e9d5ff' }}
              >
                <span style={{ fontSize: 22, lineHeight: 1.2 }}>💤</span>
                <div>
                  <div className="text-xs font-bold text-purple-800 uppercase tracking-wide mb-1">
                    Pre-Call Nap
                  </div>
                  <div className="text-sm font-semibold text-purple-900">
                    Before: {nap.before_event}
                  </div>
                  <div className="text-xs text-purple-700 font-mono mt-0.5">
                    {formatTime(nap.start_time)} – {formatTime(nap.end_time)} · Diffuse window
                  </div>
                </div>
              </div>
            ))
          ) : (
            <div
              className="flex items-start gap-3 rounded-lg px-4 py-3"
              style={{ background: '#faf5ff', border: '1px dashed #e9d5ff' }}
            >
              <span style={{ fontSize: 22, lineHeight: 1.2 }}>💤</span>
              <div>
                <div className="text-xs font-bold text-purple-600 uppercase tracking-wide mb-1">
                  Nap Protocol
                </div>
                <div className="text-sm text-purple-400 font-mono">
                  No high-stakes calls today
                </div>
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
