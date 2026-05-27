import { useState, useEffect, useRef, useCallback } from 'react';

/* ─────────────────────────────────────────
   TYPES
───────────────────────────────────────── */
type MicState = 'idle' | 'listening' | 'processing' | 'responding';

interface ServiceStatus {
  name: string;
  port: number;
  online: boolean;
}

interface ThreadMessage {
  id: number;
  role: 'user' | 'eva';
  text: string;
  card?: 'services' | 'deals' | 'calendar';
}

/* ─────────────────────────────────────────
   VOICE WS HOOK
───────────────────────────────────────── */
function useVoiceWS() {
  const [state, setState] = useState<MicState>('idle');
  const [lastTranscript, setLastTranscript] = useState('');
  const [lastResponse, setLastResponse] = useState('');
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let ws: WebSocket;
    try {
      ws = new WebSocket('ws://localhost:8774/ws');
      wsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data as string);
          if (data.type === 'state') setState(data.state as MicState);
          if (data.type === 'transcript') setLastTranscript(data.text as string);
          if (data.type === 'response') setLastResponse(data.text as string);
        } catch {}
      };

      ws.onerror = () => {
        // silently stay in demo mode
        wsRef.current = null;
      };
    } catch {
      // silently stay in demo mode
    }

    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  return { state, setState, lastTranscript, lastResponse };
}

/* ─────────────────────────────────────────
   SERVICE STATUS CARD
───────────────────────────────────────── */
const DEMO_SERVICES: ServiceStatus[] = [
  { name: 'Context API', port: 8765, online: true },
  { name: 'Deal Scout', port: 8766, online: true },
  { name: 'Content Engine', port: 8767, online: true },
  { name: 'Launcher', port: 8768, online: true },
  { name: 'Channels', port: 8770, online: true },
  { name: 'Pathfinder', port: 8773, online: true },
  { name: 'Voice', port: 8774, online: false },
];

function ServiceStatusCard() {
  return (
    <div style={{
      background: '#111111',
      border: '1px solid #1e1e1e',
      borderRadius: 12,
      padding: '16px',
      marginTop: 10,
    }}>
      <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', color: '#06b6d4', marginBottom: 12, textTransform: 'uppercase' }}>
        Service Status
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px 12px' }}>
        {DEMO_SERVICES.map(svc => (
          <div key={svc.port} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{
              width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
              background: svc.online ? '#22c55e' : '#ef4444',
              boxShadow: svc.online ? '0 0 6px rgba(34,197,94,0.5)' : '0 0 6px rgba(239,68,68,0.4)',
            }} />
            <div>
              <div style={{ fontSize: 11, color: svc.online ? '#e5e7eb' : '#6b7280' }}>{svc.name}</div>
              <div style={{ fontSize: 10, color: '#374151', fontFamily: 'ui-monospace, monospace' }}>:{svc.port}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────
   DEAL CARD
───────────────────────────────────────── */
interface DealCardData {
  name: string;
  category: string;
  price: string;
  mrr: string;
  multiple: string;
}

function DealCard({ deal }: { deal: DealCardData }) {
  return (
    <div style={{
      background: '#111111',
      border: '1px solid #1e1e1e',
      borderRadius: 12,
      padding: '14px 16px',
      flex: '1 1 0',
      minWidth: 0,
    }}>
      <div style={{ fontSize: 10, color: '#06b6d4', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 4 }}>
        {deal.category}
      </div>
      <div style={{ fontSize: 14, fontWeight: 700, color: '#ffffff', marginBottom: 8, lineHeight: 1.3 }}>{deal.name}</div>
      <div style={{ fontSize: 18, fontWeight: 700, color: '#ffffff', marginBottom: 4 }}>{deal.price}</div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 10, color: '#4b5563' }}>MRR</div>
          <div style={{ fontSize: 13, color: '#22c55e', fontWeight: 600 }}>{deal.mrr}</div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: '#4b5563' }}>Multiple</div>
          <div style={{ fontSize: 13, color: '#9ca3af' }}>{deal.multiple}</div>
        </div>
      </div>
      <div style={{ textAlign: 'right' }}>
        <span style={{ fontSize: 12, color: '#06b6d4', cursor: 'pointer' }}>View →</span>
      </div>
    </div>
  );
}

const DEMO_DEALS: DealCardData[] = [
  { name: 'Health & Wellness SaaS', category: 'SaaS', price: '$285K', mrr: '$8,400', multiple: '2.8x' },
  { name: 'Content Analytics SaaS', category: 'SaaS', price: '$192K', mrr: '$6,100', multiple: '2.6x' },
];

function DealCardsRow() {
  return (
    <div style={{ display: 'flex', gap: 10, marginTop: 10 }}>
      {DEMO_DEALS.map(d => <DealCard key={d.name} deal={d} />)}
    </div>
  );
}

/* ─────────────────────────────────────────
   CALENDAR CARD
───────────────────────────────────────── */
interface CalEvent {
  time: string;
  title: string;
  urgent?: boolean;
  color: string;
}

const DEMO_EVENTS: CalEvent[] = [
  { time: '9:00 AM', title: 'GovCon · Jay Prasad', color: '#06b6d4' },
  { time: '11:00 AM', title: 'Speaker Kit Masterclass', urgent: true, color: '#ef4444' },
  { time: '1:15 PM', title: 'Storeys f/u · Gabriela Perez', color: '#22c55e' },
];

function CalendarCard() {
  return (
    <div style={{
      background: '#111111',
      border: '1px solid #1e1e1e',
      borderRadius: 12,
      padding: '16px',
      marginTop: 10,
    }}>
      <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', color: '#06b6d4', marginBottom: 12, textTransform: 'uppercase' }}>
        Thursday, May 28
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {DEMO_EVENTS.map((ev, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 3, height: 36, borderRadius: 2, background: ev.color, flexShrink: 0 }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 11, color: '#4b5563', fontFamily: 'ui-monospace, monospace' }}>{ev.time}</div>
              <div style={{ fontSize: 13, color: '#e5e7eb' }}>{ev.title}</div>
            </div>
            {ev.urgent && (
              <span style={{
                fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
                color: '#ef4444', background: 'rgba(239,68,68,0.12)',
                padding: '2px 6px', borderRadius: 4, flexShrink: 0,
              }}>
                URGENT
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────
   THREAD MESSAGE
───────────────────────────────────────── */
function ThreadMessage({ msg, delay }: { msg: ThreadMessage; delay: number }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), delay);
    return () => clearTimeout(t);
  }, [delay]);

  if (msg.role === 'user') {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'flex-end',
          opacity: visible ? 1 : 0,
          transform: visible ? 'translateY(0)' : 'translateY(12px)',
          transition: 'opacity 400ms ease, transform 400ms ease',
        }}
      >
        <div style={{
          background: '#1a1a1a',
          border: '1px solid #2a2a2a',
          borderRadius: 16,
          padding: '10px 16px',
          fontSize: 14,
          color: '#ffffff',
          maxWidth: '80%',
        }}>
          {msg.text}
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        opacity: visible ? 1 : 0,
        transform: visible ? 'translateY(0)' : 'translateY(12px)',
        transition: 'opacity 400ms ease, transform 400ms ease',
      }}
    >
      <div style={{ fontSize: 11, fontWeight: 700, color: '#06b6d4', fontFamily: 'ui-monospace, monospace', marginBottom: 4 }}>
        EVA
      </div>
      <div style={{ fontSize: 14, color: '#e5e7eb', lineHeight: 1.7 }}>
        {msg.text}
      </div>
      {msg.card === 'services' && <ServiceStatusCard />}
      {msg.card === 'deals' && <DealCardsRow />}
      {msg.card === 'calendar' && <CalendarCard />}
    </div>
  );
}

/* ─────────────────────────────────────────
   PRE-POPULATED THREAD
───────────────────────────────────────── */
const INITIAL_THREAD: ThreadMessage[] = [
  { id: 1, role: 'user', text: 'Status of EVA services' },
  { id: 2, role: 'eva', text: '6 of 7 services are online. Voice is offline — run eva-boot.sh to start it.', card: 'services' },
  { id: 3, role: 'user', text: 'Show me today\'s deals' },
  { id: 4, role: 'eva', text: '2 new listings from Empire Flippers match your criteria.', card: 'deals' },
  { id: 5, role: 'user', text: 'What\'s on my calendar Thursday?' },
  { id: 6, role: 'eva', text: '3 events on Thursday May 28.', card: 'calendar' },
];

/* ─────────────────────────────────────────
   MIC BUTTON
───────────────────────────────────────── */
function MicButton({ state, onClick }: { state: MicState; onClick: () => void }) {
  const isListening = state === 'listening';
  const isProcessing = state === 'processing';
  const isResponding = state === 'responding';

  const ringAnimation = isListening
    ? 'micRingFast 0.8s ease-in-out infinite'
    : isResponding
    ? 'micBurst 0.6s ease-out forwards'
    : 'micRing 3s ease-in-out infinite';

  const btnBg = isListening ? '#0e2a30' : '#111111';
  const iconColor = isListening || isProcessing ? '#06b6d4' : isResponding ? '#ffffff' : '#4b5563';

  return (
    <div style={{ position: 'relative', width: 88, height: 88, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      {/* Outer ring */}
      {!isProcessing && (
        <div
          style={{
            position: 'absolute',
            width: 88,
            height: 88,
            borderRadius: '50%',
            border: `1.5px solid rgba(6,182,212,${isListening ? '0.6' : '0.2'})`,
            animation: ringAnimation,
            pointerEvents: 'none',
          }}
        />
      )}

      {/* Spinning arc for processing */}
      {isProcessing && (
        <div
          style={{
            position: 'absolute',
            width: 88,
            height: 88,
            borderRadius: '50%',
            border: '1.5px solid transparent',
            borderTopColor: '#06b6d4',
            animation: 'micSpin 1s linear infinite',
            pointerEvents: 'none',
          }}
        />
      )}

      {/* Main button */}
      <button
        onClick={onClick}
        style={{
          width: 72,
          height: 72,
          borderRadius: '50%',
          border: '1.5px solid #1e1e1e',
          background: btnBg,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          transition: 'background 200ms, border-color 200ms',
          position: 'relative',
          zIndex: 1,
        }}
      >
        {/* Mic SVG */}
        <svg
          width="28"
          height="28"
          viewBox="0 0 24 24"
          fill="none"
          stroke={iconColor}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{
            animation: isProcessing ? 'micPulse 1s ease-in-out infinite' : undefined,
            transition: 'stroke 200ms',
          }}
        >
          <path d="M12 2a3 3 0 0 1 3 3v7a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3z" />
          <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
          <line x1="12" y1="19" x2="12" y2="22" />
          <line x1="8" y1="22" x2="16" y2="22" />
        </svg>
      </button>
    </div>
  );
}

/* ─────────────────────────────────────────
   SUBTITLE TEXT
───────────────────────────────────────── */
function subtitleText(state: MicState, lastResponse: string): string {
  switch (state) {
    case 'listening': return 'Listening…';
    case 'processing': return 'Thinking…';
    case 'responding': return lastResponse ? lastResponse.slice(0, 60) + (lastResponse.length > 60 ? '…' : '') : 'Responding…';
    default: return 'What can I help with?';
  }
}

/* ─────────────────────────────────────────
   EVA HOME
───────────────────────────────────────── */
export function EVAHome() {
  const { state, setState, lastResponse } = useVoiceWS();
  const [thread] = useState<ThreadMessage[]>(INITIAL_THREAD);
  const threadRef = useRef<HTMLDivElement>(null);

  const handleMicClick = useCallback(() => {
    setState(prev => {
      const cycle: MicState[] = ['idle', 'listening', 'processing', 'responding'];
      const idx = cycle.indexOf(prev);
      return cycle[(idx + 1) % cycle.length];
    });
  }, [setState]);

  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [thread]);

  return (
    <div
      style={{
        minHeight: 'calc(100vh - 48px)',
        background: '#0a0a0a',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        paddingTop: 64,
        paddingBottom: 40,
      }}
    >
      {/* EVA Title */}
      <div
        style={{
          fontSize: 96,
          fontWeight: 100,
          color: '#ffffff',
          lineHeight: 1,
          letterSpacing: '-0.04em',
          animation: 'evaBreath 4s ease-in-out infinite',
          userSelect: 'none',
          marginBottom: 32,
        }}
      >
        EVA
      </div>

      {/* Mic button */}
      <MicButton state={state} onClick={handleMicClick} />

      {/* Subtitle */}
      <div
        style={{
          fontSize: 14,
          color: '#4b5563',
          marginTop: 16,
          marginBottom: 40,
          transition: 'color 300ms',
          textAlign: 'center',
          maxWidth: 400,
        }}
      >
        {subtitleText(state, lastResponse)}
      </div>

      {/* Conversation thread */}
      <div
        ref={threadRef}
        style={{
          width: '100%',
          maxWidth: 640,
          padding: '0 24px',
          display: 'flex',
          flexDirection: 'column',
          gap: 20,
        }}
      >
        {thread.map((msg, i) => (
          <ThreadMessage key={msg.id} msg={msg} delay={i * 120} />
        ))}
      </div>
    </div>
  );
}

export default EVAHome;
