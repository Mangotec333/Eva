import { Layers, Zap, TrendingUp, Heart, Mic, Building2, ShoppingBag, RotateCcw } from 'lucide-react';
import type { Priority, PriorityStatus } from '../types';

// ── Track Data ────────────────────────────────────────────────────────────────
const TRACKS: Priority[] = [
  {
    rank: 1,
    track: 'EVA OS',
    name: 'EVA — Autonomous AI OS',
    status: 'ACTIVE - BUILDING',
    description: '8 modules built · Command Center live · Services startup in progress',
    metric: 'Module 8 / 8',
    flywheel: true,
  },
  {
    rank: 2,
    track: 'ACQUISITION',
    name: 'Digital Business Acquisition',
    status: 'FLYWHEEL',
    description: 'HELOC $200K @ 9.5% · 4 candidates shortlisted · No LOI sent yet',
    metric: '$0 cashflow',
    flywheel: true,
  },
  {
    rank: 3,
    track: 'AGENCY',
    name: 'AI Growth Agency',
    status: '90-DAY TARGET',
    description: 'Productized AI services for SMBs · $10K/mo threshold = arrow flips',
    metric: '$0 / $10K mo',
    flywheel: true,
  },
  {
    rank: 4,
    track: 'FAMILY',
    name: 'Wife & Family',
    status: 'PROTECTED',
    description: 'Non-negotiable protected time — quality over quantity',
  },
  {
    rank: 5,
    track: 'SPEAKING',
    name: 'Public Speaking',
    status: 'QUEUED',
    description: '"Logic, Intuition & The LLM Within You" · Leadr.co · Stage prep active',
  },
  {
    rank: 6,
    track: 'STOREYS',
    name: 'Storeys / RCFE',
    status: 'BACKGROUND',
    description: 'Senior care facility under contract · Not yet cash flowing',
  },
  {
    rank: 7,
    track: 'PUREPLATE',
    name: 'Pureplate',
    status: 'BACKGROUND',
    description: 'Dropshipping e-commerce · Maintenance mode · No new investment',
  },
];

// ── Status Config ─────────────────────────────────────────────────────────────
const STATUS_CONFIG: Record<PriorityStatus, { bg: string; text: string; border: string; dot: string; label: string }> = {
  'ACTIVE - BUILDING': {
    bg: 'bg-cyan-500/10', text: 'text-cyan-400', border: 'border-cyan-500/30', dot: 'bg-cyan-400',
    label: 'ACTIVE',
  },
  'FLYWHEEL': {
    bg: 'bg-orange-500/10', text: 'text-orange-400', border: 'border-orange-500/30', dot: 'bg-orange-400',
    label: 'FLYWHEEL',
  },
  '90-DAY TARGET': {
    bg: 'bg-amber-500/10', text: 'text-amber-400', border: 'border-amber-500/30', dot: 'bg-amber-400',
    label: '90-DAY',
  },
  'PROTECTED': {
    bg: 'bg-green-500/10', text: 'text-green-400', border: 'border-green-500/30', dot: 'bg-green-400',
    label: 'PROTECTED',
  },
  'QUEUED': {
    bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/30', dot: 'bg-blue-400',
    label: 'QUEUED',
  },
  'BACKGROUND': {
    bg: 'bg-gray-700/20', text: 'text-gray-500', border: 'border-gray-700/40', dot: 'bg-gray-600',
    label: 'BACKGROUND',
  },
  'PAUSED': {
    bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/30', dot: 'bg-red-400',
    label: 'PAUSED',
  },
};

// ── Track Icons ───────────────────────────────────────────────────────────────
const TRACK_ICONS: Record<string, React.ElementType> = {
  'EVA OS':      Zap,
  'ACQUISITION': TrendingUp,
  'AGENCY':      TrendingUp,
  'FAMILY':      Heart,
  'SPEAKING':    Mic,
  'STOREYS':     Building2,
  'PUREPLATE':   ShoppingBag,
};

// ── Track Card ────────────────────────────────────────────────────────────────
function TrackCard({ track }: { track: Priority }) {
  const config = STATUS_CONFIG[track.status] ?? STATUS_CONFIG['BACKGROUND'];
  const isActive    = track.status === 'ACTIVE - BUILDING';
  const isFlywheel  = track.status === 'FLYWHEEL';
  const isBackground = track.status === 'BACKGROUND';
  const Icon = TRACK_ICONS[track.track] ?? Zap;

  return (
    <div
      className={`flex items-center gap-3 px-3 py-2 rounded border transition-colors
        ${isActive
          ? 'bg-cyan-500/5 border-cyan-500/20 hover:bg-cyan-500/10'
          : isFlywheel
          ? 'bg-orange-500/5 border-orange-500/20 hover:bg-orange-500/10'
          : isBackground
          ? 'bg-gray-800/20 border-gray-800/40 hover:bg-gray-800/40'
          : 'bg-gray-800/50 border-gray-700/50 hover:bg-gray-800'}
      `}
    >
      {/* Rank badge */}
      <div className={`flex-shrink-0 w-6 h-6 rounded flex items-center justify-center font-mono text-xs font-bold
        ${isActive ? 'bg-cyan-500/20 text-cyan-400'
        : isFlywheel ? 'bg-orange-500/20 text-orange-400'
        : 'bg-gray-700/50 text-gray-500'}`}
      >
        {track.rank}
      </div>

      {/* Icon */}
      <Icon className={`flex-shrink-0 w-3.5 h-3.5 ${
        isActive ? 'text-cyan-400' :
        isFlywheel ? 'text-orange-400' :
        isBackground ? 'text-gray-600' : 'text-gray-400'}`}
      />

      {/* Name + Description */}
      <div className="flex-1 min-w-0">
        <div className={`font-mono text-xs font-semibold leading-none mb-0.5 truncate
          ${isBackground ? 'text-gray-500' : 'text-gray-200'}`}
        >
          {track.name}
          {/* Flywheel marker */}
          {track.flywheel && (
            <span className="ml-1.5 font-mono text-[9px] text-orange-500/70">⚙ FLYWHEEL</span>
          )}
        </div>
        <div className="font-sans text-xs text-gray-600 leading-snug truncate">
          {track.description}
        </div>
      </div>

      {/* Metric (if present) */}
      {track.metric && (
        <div className="flex-shrink-0 font-mono text-[10px] text-gray-500 hidden sm:block">
          {track.metric}
        </div>
      )}

      {/* Status Pill */}
      <div className={`flex-shrink-0 flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] font-mono font-semibold
        ${config.bg} ${config.text} ${config.border}`}
      >
        <div className={`w-1.5 h-1.5 rounded-full ${config.dot} ${isActive ? 'animate-pulse' : ''}`} />
        {config.label}
      </div>
    </div>
  );
}

// ── Flywheel Summary Bar ──────────────────────────────────────────────────────
function FlywheelBar() {
  return (
    <div className="flex items-center gap-2 px-3 py-2 bg-orange-500/5 border border-orange-500/20 rounded">
      <RotateCcw className="w-3 h-3 text-orange-400 flex-shrink-0" />
      <p className="font-mono text-[10px] text-orange-400/80 leading-snug">
        <span className="font-bold text-orange-400">FLYWHEEL:</span>{' '}
        Acquisition or Agency cash → funds EVA build time → EVA accelerates everything
      </p>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────
export function PriorityStack() {
  const flywheelTracks  = TRACKS.filter(t => t.flywheel);
  const protectedTracks = TRACKS.filter(t => !t.flywheel);

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Layers className="w-4 h-4 text-cyan-400" />
        <span className="font-mono text-xs font-bold text-gray-400 tracking-widest uppercase">
          Priority Tracks
        </span>
        <span className="ml-auto font-mono text-xs text-gray-600">
          {TRACKS.length} TRACKS
        </span>
      </div>

      {/* Flywheel section */}
      <div className="flex flex-col gap-1">
        <div className="font-mono text-[10px] text-orange-500/60 tracking-widest uppercase px-1 mb-0.5">
          ⚙ Revenue Engine
        </div>
        {flywheelTracks.map(t => <TrackCard key={t.rank} track={t} />)}
      </div>

      {/* Flywheel annotation */}
      <FlywheelBar />

      {/* Protected + Queued + Background */}
      <div className="flex flex-col gap-1">
        <div className="font-mono text-[10px] text-gray-600 tracking-widest uppercase px-1 mb-0.5">
          Non-Negotiable + Background
        </div>
        {protectedTracks.map(t => <TrackCard key={t.rank} track={t} />)}
      </div>

      {/* Footer */}
      <div className="border-t border-gray-800 pt-2">
        <p className="font-mono text-[10px] text-gray-600">
          ◆ Time flows top-down. Ranks 1–3 get first allocation until $10K/mo threshold is crossed.
        </p>
      </div>
    </div>
  );
}
