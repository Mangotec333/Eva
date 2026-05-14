import type { Checkin } from '@shared/schema';

export const ENERGY_OPTIONS = [
  { value: 'full', label: 'Full charge', icon: '🔋' },
  { value: 'good', label: 'Good', icon: '⚡' },
  { value: 'okay', label: 'Okay', icon: '😐' },
  { value: 'low', label: 'Low', icon: '🪫' },
] as const;

export type EnergyValue = (typeof ENERGY_OPTIONS)[number]['value'];

export const WEEK_STATUS_OPTIONS = [
  { value: 'on_track', label: 'Yes' },
  { value: 'mostly', label: 'Mostly' },
  { value: 'off_track', label: 'Off track' },
  { value: 'unset', label: "Haven't set them" },
] as const;

export type WeekStatus = (typeof WEEK_STATUS_OPTIONS)[number]['value'];

export const HORIZONS = [
  { key: 'month', label: 'This month' },
  { key: 'quarter', label: 'This quarter' },
  { key: 'year', label: 'This year' },
  { key: 'three_year', label: '3 years' },
  { key: 'life', label: 'Life' },
] as const;

export function todayLocalISO(): string {
  return new Date().toISOString().slice(0, 10);
}

export function formatLongDate(d: Date = new Date()): string {
  return d.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });
}

export function energyLabel(v: string | null | undefined): string {
  const o = ENERGY_OPTIONS.find((e) => e.value === v);
  return o ? `${o.icon} ${o.label}` : '—';
}

export function parseGoals(c: Pick<Checkin, 'goals'> | null | undefined): string[] {
  if (!c?.goals) return [];
  try {
    const arr = JSON.parse(c.goals);
    return Array.isArray(arr) ? arr.filter(Boolean) : [];
  } catch {
    return [];
  }
}

// Streak: consecutive days back from today (or yesterday if no today entry yet).
export function computeStreak(checkins: Pick<Checkin, 'date'>[]): number {
  if (!checkins.length) return 0;
  const set = new Set(checkins.map((c) => c.date));
  let streak = 0;
  const cursor = new Date();
  // If today missing but yesterday exists, allow streak from yesterday
  const today = cursor.toISOString().slice(0, 10);
  if (!set.has(today)) {
    cursor.setDate(cursor.getDate() - 1);
  }
  while (true) {
    const iso = cursor.toISOString().slice(0, 10);
    if (set.has(iso)) {
      streak += 1;
      cursor.setDate(cursor.getDate() - 1);
    } else {
      break;
    }
  }
  return streak;
}
