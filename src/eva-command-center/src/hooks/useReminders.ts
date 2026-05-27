import { useState, useEffect, useCallback, useRef } from 'react';

const REMINDERS_API = 'http://localhost:8767';
const POLL_INTERVAL = 60_000; // 60 seconds
const DUE_ALERT_WINDOW_MS = 15 * 60 * 1000; // 15 minutes
const LS_KEY = 'eva_reminders_local';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface Reminder {
  id: string;
  title: string;
  due_at: string; // ISO string
  tag?: string;
  done: boolean;
  created_at: string;
}

export interface CalendarEvent {
  id: string;
  title: string;
  start: string; // ISO string
  end: string;
  calendar: string;
  color?: string;
}

// ─── Pre-seeded LinkedIn token reminder ──────────────────────────────────────

const SEED_REMINDER: Reminder = {
  id: 'seed-linkedin-token',
  title: 'Refresh LinkedIn token',
  due_at: '2026-07-12T09:00:00.000Z',
  tag: 'linkedin',
  done: false,
  created_at: new Date().toISOString(),
};

function loadLocalReminders(): Reminder[] {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as Reminder[];
  } catch {
    return [];
  }
}

function saveLocalReminders(reminders: Reminder[]): void {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(reminders));
  } catch {
    // ignore storage errors
  }
}

function ensureSeed(): Reminder[] {
  const stored = loadLocalReminders();
  const hasSeed = stored.some(r => r.id === SEED_REMINDER.id);
  if (!hasSeed) {
    const seeded = [SEED_REMINDER, ...stored];
    saveLocalReminders(seeded);
    return seeded;
  }
  return stored;
}

// ─── Hook result type ─────────────────────────────────────────────────────────

export interface UseRemindersResult {
  reminders: Reminder[];
  calendarEvents: CalendarEvent[];
  loading: boolean;
  calendarLoading: boolean;
  isOnline: boolean;
  dueAlerts: Reminder[];
  addReminder: (title: string, due_at: string, tag?: string) => Promise<void>;
  toggleDone: (id: string) => Promise<void>;
  deleteReminder: (id: string) => Promise<void>;
  dismissAlert: (id: string) => void;
  refresh: () => void;
}

// ─── Hook implementation ──────────────────────────────────────────────────────

export function useReminders(): UseRemindersResult {
  const [reminders, setReminders]           = useState<Reminder[]>(() => ensureSeed());
  const [calendarEvents, setCalendarEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading]               = useState(true);
  const [calendarLoading, setCalendarLoading] = useState(true);
  const [isOnline, setIsOnline]             = useState(false);
  const [dueAlerts, setDueAlerts]           = useState<Reminder[]>([]);
  const dismissedRef                        = useRef<Set<string>>(new Set());

  // ── Fetch reminders from backend ──────────────────────────────────────────

  const fetchReminders = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetch(`${REMINDERS_API}/reminders`, {
        signal: AbortSignal.timeout(5000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: Reminder[] = await res.json();
      setReminders(data);
      saveLocalReminders(data);
      setIsOnline(true);
    } catch {
      // Fall back to localStorage
      const local = loadLocalReminders();
      setReminders(local.length ? local : ensureSeed());
      setIsOnline(false);
    } finally {
      setLoading(false);
    }
  }, []);

  // ── Fetch calendar events ─────────────────────────────────────────────────

  const fetchCalendar = useCallback(async () => {
    try {
      setCalendarLoading(true);
      const res = await fetch(`${REMINDERS_API}/reminders/calendar`, {
        signal: AbortSignal.timeout(5000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: CalendarEvent[] = await res.json();
      setCalendarEvents(Array.isArray(data) ? data : []);
    } catch {
      setCalendarEvents([]);
    } finally {
      setCalendarLoading(false);
    }
  }, []);

  // ── Due alert checker ─────────────────────────────────────────────────────

  const checkDueAlerts = useCallback((current: Reminder[]) => {
    const now = Date.now();
    const alerts = current.filter(r => {
      if (r.done) return false;
      if (dismissedRef.current.has(r.id)) return false;
      const due = new Date(r.due_at).getTime();
      return due > now && due - now <= DUE_ALERT_WINDOW_MS;
    });
    setDueAlerts(alerts);
  }, []);

  // ── Polling ───────────────────────────────────────────────────────────────

  useEffect(() => {
    fetchReminders();
    fetchCalendar();

    const dataInterval = setInterval(() => {
      fetchReminders();
      fetchCalendar();
    }, POLL_INTERVAL);

    return () => clearInterval(dataInterval);
  }, [fetchReminders, fetchCalendar]);

  // Check due alerts whenever reminders change and on a 60s tick
  useEffect(() => {
    checkDueAlerts(reminders);
    const alertInterval = setInterval(() => checkDueAlerts(reminders), POLL_INTERVAL);
    return () => clearInterval(alertInterval);
  }, [reminders, checkDueAlerts]);

  // ── CRUD operations ───────────────────────────────────────────────────────

  const addReminder = useCallback(async (title: string, due_at: string, tag?: string) => {
    const optimisticId = `local-${Date.now()}`;
    const optimistic: Reminder = {
      id: optimisticId,
      title,
      due_at,
      tag,
      done: false,
      created_at: new Date().toISOString(),
    };

    if (!isOnline) {
      // Offline — persist locally only
      setReminders(prev => {
        const updated = [...prev, optimistic].sort(
          (a, b) => new Date(a.due_at).getTime() - new Date(b.due_at).getTime()
        );
        saveLocalReminders(updated);
        return updated;
      });
      return;
    }

    try {
      const res = await fetch(`${REMINDERS_API}/reminders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, due_at, tag }),
        signal: AbortSignal.timeout(8000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const created: Reminder = await res.json();
      setReminders(prev => {
        const updated = [...prev, created].sort(
          (a, b) => new Date(a.due_at).getTime() - new Date(b.due_at).getTime()
        );
        saveLocalReminders(updated);
        return updated;
      });
    } catch {
      // Fall back to local
      setReminders(prev => {
        const updated = [...prev, optimistic].sort(
          (a, b) => new Date(a.due_at).getTime() - new Date(b.due_at).getTime()
        );
        saveLocalReminders(updated);
        return updated;
      });
    }
  }, [isOnline]);

  const toggleDone = useCallback(async (id: string) => {
    // Optimistic update
    let newDone = false;
    setReminders(prev => {
      const updated = prev.map(r => {
        if (r.id === id) {
          newDone = !r.done;
          return { ...r, done: newDone };
        }
        return r;
      });
      saveLocalReminders(updated);
      return updated;
    });

    if (!isOnline) return;

    try {
      const res = await fetch(`${REMINDERS_API}/reminders/${id}/done`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ done: newDone }),
        signal: AbortSignal.timeout(5000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
    } catch {
      // Optimistic already applied; silently ignore
    }
  }, [isOnline]);

  const deleteReminder = useCallback(async (id: string) => {
    // Optimistic
    setReminders(prev => {
      const updated = prev.filter(r => r.id !== id);
      saveLocalReminders(updated);
      return updated;
    });
    dismissedRef.current.delete(id);

    if (!isOnline) return;

    try {
      const res = await fetch(`${REMINDERS_API}/reminders/${id}`, {
        method: 'DELETE',
        signal: AbortSignal.timeout(5000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
    } catch {
      // Silently ignore — already removed from UI
    }
  }, [isOnline]);

  const dismissAlert = useCallback((id: string) => {
    dismissedRef.current.add(id);
    setDueAlerts(prev => prev.filter(r => r.id !== id));
  }, []);

  return {
    reminders,
    calendarEvents,
    loading,
    calendarLoading,
    isOnline,
    dueAlerts,
    addReminder,
    toggleDone,
    deleteReminder,
    dismissAlert,
    refresh: fetchReminders,
  };
}
