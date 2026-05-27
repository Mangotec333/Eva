import { useState } from 'react';

/* ─────────────────────────────────────────
   USERS TABLE
───────────────────────────────────────── */
interface User {
  name: string;
  email: string;
  role: 'Admin' | 'User' | 'Viewer';
  status: 'Active' | 'Inactive';
}

const USERS: User[] = [
  { name: 'Vineet Ravi', email: 'vineetkumar@mangotecusa.com', role: 'Admin', status: 'Active' },
  { name: 'Demo User', email: 'demo@mangotecusa.com', role: 'User', status: 'Active' },
  { name: 'Guest', email: '—', role: 'Viewer', status: 'Inactive' },
];

const ROLE_STYLE: Record<User['role'], { bg: string; color: string }> = {
  Admin:  { bg: 'rgba(6,182,212,0.12)',  color: '#06b6d4' },
  User:   { bg: 'rgba(59,130,246,0.12)', color: '#3b82f6' },
  Viewer: { bg: '#1e1e1e',               color: '#6b7280' },
};

function UsersPanel() {
  return (
    <div style={{
      background: '#111111',
      border: '1px solid #1e1e1e',
      borderRadius: 16,
      overflow: 'hidden',
      flex: '1 1 0',
      minWidth: 0,
    }}>
      <div style={{ padding: '20px 20px 16px', borderBottom: '1px solid #1e1e1e' }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, color: '#ffffff', margin: 0 }}>Users</h2>
      </div>

      <div style={{ padding: '0 20px 20px' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              {['Name', 'Role', 'Status'].map(h => (
                <th
                  key={h}
                  style={{
                    textAlign: 'left',
                    fontSize: 10,
                    fontWeight: 700,
                    letterSpacing: '0.06em',
                    textTransform: 'uppercase',
                    color: '#4b5563',
                    padding: '16px 0 10px',
                    paddingRight: 20,
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {USERS.map((user, i) => (
              <tr key={i} style={{ borderTop: '1px solid #1a1a1a' }}>
                <td style={{ padding: '12px 20px 12px 0' }}>
                  <div style={{ fontSize: 14, color: '#ffffff', fontWeight: 500 }}>{user.name}</div>
                  <div style={{ fontSize: 11, color: '#4b5563', marginTop: 1 }}>{user.email}</div>
                </td>
                <td style={{ padding: '12px 20px 12px 0' }}>
                  <span style={{
                    fontSize: 11,
                    fontWeight: 600,
                    padding: '3px 10px',
                    borderRadius: 20,
                    ...ROLE_STYLE[user.role],
                  }}>
                    {user.role}
                  </span>
                </td>
                <td style={{ padding: '12px 0' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{
                      width: 6,
                      height: 6,
                      borderRadius: '50%',
                      background: user.status === 'Active' ? '#22c55e' : '#374151',
                      boxShadow: user.status === 'Active' ? '0 0 6px rgba(34,197,94,0.5)' : 'none',
                    }} />
                    <span style={{ fontSize: 13, color: user.status === 'Active' ? '#9ca3af' : '#4b5563' }}>
                      {user.status}
                    </span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────
   SERVICES PANEL
───────────────────────────────────────── */
interface Service {
  name: string;
  port: string;
}

const SERVICES: Service[] = [
  { name: 'Context API',   port: ':8765' },
  { name: 'Deal Scout',    port: ':8766' },
  { name: 'Content Engine', port: ':8767' },
  { name: 'Launcher',      port: ':8768' },
  { name: 'Channels Hub',  port: ':8770' },
  { name: 'Pathfinder',    port: ':8773' },
  { name: 'Voice',         port: ':8774' },
];

function ToggleSwitch({ on, onToggle }: { on: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className={`eva-toggle${on ? ' on' : ''}`}
      aria-label={on ? 'Turn off' : 'Turn on'}
    />
  );
}

function ServicesPanel() {
  const [states, setStates] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {};
    SERVICES.forEach(s => { init[s.port] = s.port !== ':8774'; });
    return init;
  });

  const toggle = (port: string) => {
    setStates(prev => ({ ...prev, [port]: !prev[port] }));
  };

  return (
    <div style={{
      background: '#111111',
      border: '1px solid #1e1e1e',
      borderRadius: 16,
      overflow: 'hidden',
      flex: '1 1 0',
      minWidth: 0,
    }}>
      <div style={{ padding: '20px 20px 16px', borderBottom: '1px solid #1e1e1e' }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, color: '#ffffff', margin: 0 }}>Services</h2>
      </div>

      <div style={{ padding: '8px 20px 20px' }}>
        {SERVICES.map(svc => {
          const online = states[svc.port] ?? false;
          return (
            <div
              key={svc.port}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '12px 0',
                borderBottom: '1px solid #161616',
              }}
            >
              {/* Status dot */}
              <span style={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                flexShrink: 0,
                background: online ? '#22c55e' : '#374151',
                boxShadow: online ? '0 0 6px rgba(34,197,94,0.5)' : 'none',
              }} />

              {/* Name */}
              <span style={{ flex: 1, fontSize: 14, color: online ? '#e5e7eb' : '#6b7280' }}>
                {svc.name}
              </span>

              {/* Port */}
              <span style={{
                fontSize: 11,
                color: '#374151',
                fontFamily: 'ui-monospace, SFMono-Regular, monospace',
                marginRight: 12,
              }}>
                {svc.port}
              </span>

              {/* Toggle */}
              <ToggleSwitch on={online} onToggle={() => toggle(svc.port)} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────
   ADMIN VIEW
───────────────────────────────────────── */
export function AdminView() {
  return (
    <div style={{ padding: '40px 48px', maxWidth: 1280, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: 28, fontWeight: 600, color: '#ffffff', margin: 0, letterSpacing: '-0.02em' }}>
          Admin
        </h1>
        <p style={{ fontSize: 13, color: '#9ca3af', marginTop: 4 }}>
          Users · Services · Configuration
        </p>
      </div>

      {/* Two-panel layout */}
      <div style={{
        display: 'flex',
        gap: 16,
        flexWrap: 'wrap',
        alignItems: 'flex-start',
      }}>
        <UsersPanel />
        <ServicesPanel />
      </div>
    </div>
  );
}

export default AdminView;
