/**
 * GlossaiPanel — GLŌSSAI organic beauty module
 * Embeds smart-beauty-guide.lovable.app within EVA Personal stack
 */

import { useState } from 'react';

const GLOSSAI_URL = 'https://smart-beauty-guide.lovable.app';

export function GlossaiPanel() {
  const [loaded, setLoaded] = useState(false);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Brand bar */}
      <div className="eva-card" style={{
        padding: '16px 20px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 10,
            background: 'linear-gradient(135deg, #1a1a1a 0%, #3d3d3d 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 18,
          }}>
            ✨
          </div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.01em' }}>
              GLŌSSAI
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 1 }}>
              Your skin. Your rules. Zero toxic guesswork.
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            fontSize: 10, fontWeight: 600, padding: '3px 9px',
            borderRadius: 8, background: '#ECFDF5', color: '#00C07F',
            letterSpacing: '0.03em',
          }}>
            LIVE
          </span>
          <a
            href={GLOSSAI_URL}
            target="_blank"
            rel="noreferrer"
            style={{
              fontSize: 11, color: 'var(--text-tertiary)',
              textDecoration: 'none', padding: '4px 10px',
              border: '1px solid var(--border)',
              borderRadius: 6, background: 'var(--bg-secondary)',
            }}
          >
            Open full ↗
          </a>
        </div>
      </div>

      {/* Thesis strip */}
      <div style={{
        padding: '12px 18px',
        background: 'linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%)',
        borderRadius: 10,
        display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12,
      }}>
        {[
          { icon: '🌿', label: 'Inside-out beauty', desc: 'Nutrition, sleep, gut — the foundation' },
          { icon: '🏛️', label: 'Body as temple', desc: 'The creator\'s design at 100%' },
          { icon: '♾️', label: 'Lasting change', desc: 'No injections. No shortcuts.' },
        ].map(item => (
          <div key={item.label} style={{ textAlign: 'center', padding: '8px 4px' }}>
            <div style={{ fontSize: 22, marginBottom: 4 }}>{item.icon}</div>
            <div style={{ fontSize: 11, fontWeight: 600, color: '#FFFFFF', marginBottom: 2 }}>{item.label}</div>
            <div style={{ fontSize: 10, color: '#9CA3AF' }}>{item.desc}</div>
          </div>
        ))}
      </div>

      {/* Embedded app */}
      <div className="eva-card" style={{ padding: 0, overflow: 'hidden', position: 'relative' }}>
        {!loaded && (
          <div style={{
            position: 'absolute', inset: 0, zIndex: 2,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'var(--bg)', flexDirection: 'column', gap: 8,
          }}>
            <div style={{ fontSize: 24 }}>✨</div>
            <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>Loading GLŌSSAI…</div>
          </div>
        )}
        <iframe
          src={GLOSSAI_URL}
          title="GLŌSSAI — Organic Beauty Intelligence"
          onLoad={() => setLoaded(true)}
          style={{
            width: '100%',
            height: 720,
            border: 'none',
            display: 'block',
            opacity: loaded ? 1 : 0,
            transition: 'opacity 400ms ease',
          }}
          allow="fullscreen"
        />
      </div>

      {/* Funnel note */}
      <div style={{
        padding: '10px 16px',
        background: 'var(--bg-secondary)',
        borderRadius: 8,
        fontSize: 11, color: 'var(--text-tertiary)',
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <span>🌱</span>
        <span>
          GLŌSSAI founding member signups feed the <strong style={{ color: 'var(--text-secondary)' }}>Incubator</strong> pipeline via Pathfinder.
        </span>
      </div>
    </div>
  );
}
