import { useState, useEffect, useRef } from 'react';
import {
  Bell,
  Plus,
  X,
  Check,
  Calendar,
  Clock,
  Tag,
  WifiOff,
  Loader2,
} from 'lucide-react';
import { useReminders, type Reminder, type CalendarEvent } from '../hooks/useReminders';

// ─── Re-export types for consumers ───────────────────────────────────────────
export type { Reminder, CalendarEvent };

// ─── Helpers ──────────────────────────────────────────────────────────────────

function isToday(isoString: string): boolean {
  const d = new Date(isoString);
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

function isTomorrow(isoString: string): boolean {
  const d = new Date(isoString);
  const tom = new Date();
  tom.setDate(tom.getDate() + 1);
  return (
    d.getFullYear() === tom.getFullYear() &&
    d.getMonth() === tom.getMonth() &&
    d.getDate() === tom.getDate()
  );
}

function isOverdue(isoString: string): boolean {
  return new Date(isoString).getTime() < Date.now();
}

function formatTime(isoString: string): string {
  try {
    return new Date(isoString).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    });
  } catch {
    return '';
  }
}

function formatDateTime(isoString: string): string {
  try {
    const d = new Date(isoString);
    if (isToday(isoString)) return `Today ${formatTime(isoString)}`;
    if (isTomorrow(isoString)) return `Tomorrow ${formatTime(isoString)}`;
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' + formatTime(isoString);
  } catch {
    return isoString;
  }
}

function dueBadgeClass(due_at: string, done: boolean): string {
  if (done) return 'text-gray-500 bg-gray-100 border-gray-200';
  if (isOverdue(due_at)) return 'text-red-400 bg-red-400/10 border-red-400/30';
  if (isToday(due_at)) return 'text-yellow-400 bg-yellow-400/10 border-yellow-400/30';
  return 'text-gray-500 bg-gray-100 border-gray-200';
}

function calendarDotClass(start: string): string {
  if (isToday(start)) return 'bg-cyan-400';
  if (isTomorrow(start)) return 'bg-yellow-400';
  return 'bg-gray-500';
}

// ─── Inline Add Form ──────────────────────────────────────────────────────────

interface AddFormProps {
  onSave: (title: string, due_at: string, tag?: string) => Promise<void>;
  onCancel: () => void;
}

function AddForm({ onSave, onCancel }: AddFormProps) {
  const [title, setTitle]   = useState('');
  const [due, setDue]       = useState('');
  const [tag, setTag]       = useState('');
  const [saving, setSaving] = useState(false);
  const titleRef            = useRef<HTMLInputElement>(null);

  useEffect(() => {
    titleRef.current?.focus();
  }, []);

  const handleSave = async () => {
    if (!title.trim() || !due) return;
    setSaving(true);
    try {
      await onSave(title.trim(), new Date(due).toISOString(), tag.trim() || undefined);
      onCancel();
    } finally {
      setSaving(false);
    }
  };

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSave();
    if (e.key === 'Escape') onCancel();
  };

  return (
    <div className="mt-3 bg-white border border-cyan-400/20 rounded-lg p-3 space-y-2">
      <input
        ref={titleRef}
        type="text"
        placeholder="Reminder title..."
        value={title}
        onChange={e => setTitle(e.target.value)}
        onKeyDown={handleKey}
        className="w-full bg-gray-50 border border-gray-200 rounded px-3 py-1.5 text-sm text-gray-800 placeholder-gray-600 focus:outline-none focus:border-cyan-400/50 font-mono"
      />
      <div className="flex gap-2">
        <input
          type="datetime-local"
          value={due}
          onChange={e => setDue(e.target.value)}
          onKeyDown={handleKey}
          className="flex-1 bg-gray-50 border border-gray-200 rounded px-3 py-1.5 text-sm text-gray-800 focus:outline-none focus:border-cyan-400/50 font-mono [color-scheme:dark]"
        />
        <input
          type="text"
          placeholder="tag (optional)"
          value={tag}
          onChange={e => setTag(e.target.value)}
          onKeyDown={handleKey}
          className="w-32 bg-gray-50 border border-gray-200 rounded px-3 py-1.5 text-sm text-gray-800 placeholder-gray-600 focus:outline-none focus:border-cyan-400/50 font-mono"
        />
      </div>
      <div className="flex gap-2 justify-end">
        <button
          onClick={onCancel}
          className="px-3 py-1 text-xs font-mono text-gray-500 hover:text-gray-800 border border-gray-200 rounded hover:border-gray-500 transition-colors"
        >
          CANCEL
        </button>
        <button
          onClick={handleSave}
          disabled={!title.trim() || !due || saving}
          className="px-3 py-1 text-xs font-mono bg-cyan-400/10 border border-cyan-400/30 text-cyan-400 hover:bg-cyan-400/20 rounded transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
        >
          {saving ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />}
          SAVE
        </button>
      </div>
    </div>
  );
}

// ─── Calendar Event Card ──────────────────────────────────────────────────────

function CalendarCard({ event }: { event: CalendarEvent }) {
  return (
    <div className="flex-shrink-0 w-40 bg-white border border-gray-200 rounded-lg p-2.5 space-y-1">
      <div className="flex items-center gap-1.5">
        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${calendarDotClass(event.start)}`} />
        <span className="font-mono text-xs text-gray-500 truncate">
          {formatTime(event.start)}
        </span>
        <span className="ml-auto font-mono text-[9px] text-cyan-400/70 border border-cyan-400/20 rounded px-1 py-px bg-cyan-400/5">
          GCAL
        </span>
      </div>
      <p className="text-xs text-gray-500 leading-tight line-clamp-2">{event.title}</p>
    </div>
  );
}

// ─── Reminder Row ─────────────────────────────────────────────────────────────

interface ReminderRowProps {
  reminder: Reminder;
  onToggle: (id: string) => void;
  onDelete: (id: string) => void;
}

function ReminderRow({ reminder, onToggle, onDelete }: ReminderRowProps) {
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    setDeleting(true);
    await onDelete(reminder.id);
  };

  return (
    <div
      className={`flex items-center gap-2.5 py-2 px-1 border-b border-gray-200/50 last:border-0 group transition-opacity ${
        deleting ? 'opacity-0 duration-300' : 'opacity-100'
      }`}
    >
      {/* Checkbox */}
      <button
        onClick={() => onToggle(reminder.id)}
        className={`flex-shrink-0 w-4 h-4 rounded border transition-colors ${
          reminder.done
            ? 'bg-cyan-400/20 border-cyan-400/40 text-cyan-400'
            : 'border-gray-300 hover:border-cyan-400/50'
        } flex items-center justify-center`}
        aria-label={reminder.done ? 'Mark undone' : 'Mark done'}
      >
        {reminder.done && <Check size={10} />}
      </button>

      {/* Title */}
      <span
        className={`flex-1 text-sm transition-all duration-300 ${
          reminder.done
            ? 'opacity-40 line-through text-gray-500 decoration-gray-600'
            : 'text-gray-800'
        }`}
      >
        {reminder.title}
      </span>

      {/* Tag chip */}
      {reminder.tag && (
        <span className="flex-shrink-0 hidden sm:flex items-center gap-1 font-mono text-[10px] text-purple-400/80 border border-purple-400/20 bg-purple-400/5 rounded px-1.5 py-px">
          <Tag size={8} />
          {reminder.tag}
        </span>
      )}

      {/* Due date badge */}
      <span
        className={`flex-shrink-0 font-mono text-[10px] border rounded px-1.5 py-px whitespace-nowrap ${dueBadgeClass(
          reminder.due_at,
          reminder.done
        )}`}
      >
        {formatDateTime(reminder.due_at)}
      </span>

      {/* Delete */}
      <button
        onClick={handleDelete}
        className="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity text-gray-500 hover:text-red-400"
        aria-label="Delete reminder"
      >
        <X size={13} />
      </button>
    </div>
  );
}

// ─── Due Alert Toast ──────────────────────────────────────────────────────────

interface DueAlertProps {
  reminder: Reminder;
  onDismiss: (id: string) => void;
}

function DueAlert({ reminder, onDismiss }: DueAlertProps) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(reminder.id), 10_000);
    return () => clearTimeout(timer);
  }, [reminder.id, onDismiss]);

  return (
    <div className="fixed bottom-4 right-4 z-50 bg-gray-50 border border-cyan-400/50 rounded-lg p-4 shadow-lg shadow-cyan-400/10 animate-pulse w-72 max-w-[calc(100vw-2rem)]">
      <div className="flex items-start gap-2">
        <Bell size={14} className="text-cyan-400 flex-shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <p className="font-mono text-[10px] text-cyan-400 tracking-widest mb-0.5">
            REMINDER DUE SOON
          </p>
          <p className="text-sm text-gray-800 leading-tight truncate">{reminder.title}</p>
          <p className="font-mono text-xs text-yellow-400 mt-1">
            {formatDateTime(reminder.due_at)}
          </p>
        </div>
        <button
          onClick={() => onDismiss(reminder.id)}
          className="flex-shrink-0 text-gray-500 hover:text-gray-800 transition-colors"
          aria-label="Dismiss alert"
        >
          <X size={13} />
        </button>
      </div>
      <button
        onClick={() => onDismiss(reminder.id)}
        className="mt-3 w-full text-center font-mono text-[10px] text-cyan-400 border border-cyan-400/30 rounded py-1 hover:bg-cyan-400/10 transition-colors tracking-widest"
      >
        DISMISS
      </button>
    </div>
  );
}

// ─── Main RemindersPanel ──────────────────────────────────────────────────────

export default function RemindersPanel() {
  const {
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
  } = useReminders();

  const [showAddForm, setShowAddForm] = useState(false);

  const activeReminders = reminders.filter(r => !r.done);
  const doneReminders   = reminders.filter(r => r.done);

  return (
    <>
      {/* ── Panel ─────────────────────────────────────────────────────────── */}
      <div className="bg-gray-50 border border-gray-200 rounded-lg flex flex-col h-full min-h-0">

        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 flex-shrink-0">
          <div className="flex items-center gap-2">
            <Bell size={13} className="text-cyan-400" />
            <span className="font-mono text-xs tracking-widest text-gray-500 uppercase">
              Reminders
            </span>
            {!isOnline && (
              <span className="flex items-center gap-1 font-mono text-[9px] text-yellow-400/70 border border-yellow-400/20 bg-yellow-400/5 rounded px-1.5 py-px">
                <WifiOff size={8} />
                OFFLINE
              </span>
            )}
          </div>
          <button
            onClick={() => setShowAddForm(v => !v)}
            className="flex items-center gap-1 bg-cyan-400/10 border border-cyan-400/30 text-cyan-400 hover:bg-cyan-400/20 font-mono text-[10px] tracking-widest rounded px-2 py-1 transition-colors"
          >
            <Plus size={11} />
            ADD
          </button>
        </div>

        <div className="flex-1 overflow-y-auto min-h-0">

          {/* Inline Add Form */}
          {showAddForm && (
            <div className="px-4">
              <AddForm
                onSave={addReminder}
                onCancel={() => setShowAddForm(false)}
              />
            </div>
          )}

          {/* Today's Events Strip */}
          <div className="px-4 pt-3 pb-1 flex-shrink-0">
            <div className="flex items-center gap-1.5 mb-2">
              <Calendar size={11} className="text-gray-500" />
              <span className="font-mono text-[10px] tracking-widest text-gray-500 uppercase">
                Upcoming Events
              </span>
            </div>

            {calendarLoading ? (
              <div className="flex items-center gap-2 py-2">
                <Loader2 size={12} className="animate-spin text-gray-500" />
                <span className="text-xs text-gray-500 font-mono">Loading calendar…</span>
              </div>
            ) : calendarEvents.length === 0 ? (
              <div className="py-2 text-[11px] text-gray-500 font-mono">
                No upcoming events · Connect Google Calendar to populate
              </div>
            ) : (
              <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-none">
                {calendarEvents.map(ev => (
                  <CalendarCard key={ev.id} event={ev} />
                ))}
              </div>
            )}
          </div>

          {/* Divider */}
          <div className="mx-4 border-t border-gray-200 my-1" />

          {/* Reminders List */}
          <div className="px-4 pt-2 pb-3">
            <div className="flex items-center gap-1.5 mb-2">
              <Clock size={11} className="text-gray-500" />
              <span className="font-mono text-[10px] tracking-widest text-gray-500 uppercase">
                Reminders
              </span>
              {activeReminders.length > 0 && (
                <span className="ml-1 bg-cyan-400/10 border border-cyan-400/20 text-cyan-400 font-mono text-[9px] rounded-full px-1.5 py-px">
                  {activeReminders.length}
                </span>
              )}
            </div>

            {loading ? (
              <div className="flex items-center gap-2 py-3">
                <Loader2 size={12} className="animate-spin text-gray-500" />
                <span className="text-xs text-gray-500 font-mono">Loading reminders…</span>
              </div>
            ) : reminders.length === 0 ? (
              <p className="text-xs text-gray-500 font-mono py-3 text-center">
                No reminders — press ADD to create one
              </p>
            ) : (
              <div>
                {/* Active reminders */}
                {activeReminders.map(r => (
                  <ReminderRow
                    key={r.id}
                    reminder={r}
                    onToggle={toggleDone}
                    onDelete={deleteReminder}
                  />
                ))}

                {/* Done reminders — collapsed section */}
                {doneReminders.length > 0 && (
                  <details className="mt-2 group">
                    <summary className="font-mono text-[10px] text-gray-500 hover:text-gray-500 cursor-pointer select-none list-none flex items-center gap-1 py-1">
                      <span className="border border-gray-200 rounded px-1.5 py-px bg-gray-100/50 hover:bg-gray-200/50 transition-colors">
                        {doneReminders.length} DONE
                      </span>
                    </summary>
                    <div className="mt-1">
                      {doneReminders.map(r => (
                        <ReminderRow
                          key={r.id}
                          reminder={r}
                          onToggle={toggleDone}
                          onDelete={deleteReminder}
                        />
                      ))}
                    </div>
                  </details>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Due Alert Toasts ────────────────────────────────────────────────── */}
      {dueAlerts.map((alert, i) => (
        <div
          key={alert.id}
          style={{ bottom: `${1 + i * 6}rem` }}
          className="fixed right-4 z-50"
        >
          <DueAlert reminder={alert} onDismiss={dismissAlert} />
        </div>
      ))}
    </>
  );
}
