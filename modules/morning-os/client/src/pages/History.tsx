import { useQuery } from '@tanstack/react-query';
import type { Checkin } from '@shared/schema';
import { EvaLayout } from '@/components/EvaLayout';
import { computeStreak, energyLabel, parseGoals } from '@/lib/eva';
import { Flame } from 'lucide-react';

function formatShort(date: string) {
  const d = new Date(date + 'T00:00:00');
  return d.toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  });
}

// Determine which checkins form the current contiguous streak
function streakDateSet(rows: Checkin[]): Set<string> {
  const dates = new Set(rows.map((r) => r.date));
  const result = new Set<string>();
  const cursor = new Date();
  const today = cursor.toISOString().slice(0, 10);
  if (!dates.has(today)) cursor.setDate(cursor.getDate() - 1);
  while (true) {
    const iso = cursor.toISOString().slice(0, 10);
    if (dates.has(iso)) {
      result.add(iso);
      cursor.setDate(cursor.getDate() - 1);
    } else break;
  }
  return result;
}

export default function HistoryPage() {
  const q = useQuery<Checkin[]>({ queryKey: ['/api/checkins'] });
  const rows = q.data ?? [];
  const streak = computeStreak(rows);
  const streakSet = streakDateSet(rows);

  return (
    <EvaLayout>
      <div className="max-w-5xl mx-auto px-6 md:px-10 py-10 md:py-16 eva-fade-in">
        <div className="flex items-end justify-between flex-wrap gap-4 mb-10">
          <div>
            <div className="text-[11px] uppercase tracking-[0.18em] text-primary/80 mb-3">
              History
            </div>
            <h1
              className="font-medium leading-tight"
              style={{ fontSize: 'clamp(1.6rem, 3.2vw, 2.1rem)' }}
            >
              The pattern of your mornings.
            </h1>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <Flame className="h-4 w-4 text-primary" />
            <span className="tabular-nums" data-testid="text-history-streak">
              {streak}
            </span>
            <span className="text-muted-foreground">
              day {streak === 1 ? 'streak' : 'streak'}
            </span>
          </div>
        </div>

        {q.isLoading ? (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="h-14 rounded-md border border-card-border bg-card animate-pulse"
              />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <div className="border border-card-border rounded-lg bg-card p-10 text-center">
            <p className="text-muted-foreground">No check-ins yet.</p>
            <p className="text-sm text-muted-foreground mt-2">
              Complete your first morning ritual to start the pattern.
            </p>
          </div>
        ) : (
          <div className="border border-card-border rounded-lg bg-card overflow-hidden">
            <div className="hidden md:grid grid-cols-[160px_140px_1fr_80px_60px] gap-4 px-5 py-3 text-[11px] uppercase tracking-[0.16em] text-muted-foreground border-b border-card-border">
              <div>Date</div>
              <div>Energy</div>
              <div>Priority</div>
              <div className="text-right">Goals</div>
              <div className="text-right">Streak</div>
            </div>
            {rows.map((r) => {
              const onStreak = streakSet.has(r.date);
              return (
                <div
                  key={r.id}
                  data-testid={`row-checkin-${r.date}`}
                  className="grid md:grid-cols-[160px_140px_1fr_80px_60px] gap-x-4 gap-y-1 px-5 py-4 border-b border-card-border last:border-b-0 text-sm hover-elevate"
                >
                  <div className="font-medium" data-testid={`text-date-${r.date}`}>
                    {formatShort(r.date)}
                  </div>
                  <div className="text-muted-foreground md:text-foreground">
                    {energyLabel(r.energy)}
                  </div>
                  <div className="eva-accent font-medium md:font-normal md:text-foreground truncate">
                    {r.priority}
                  </div>
                  <div className="text-right tabular-nums text-muted-foreground">
                    {parseGoals(r).length}
                  </div>
                  <div className="text-right">
                    {onStreak ? (
                      <Flame className="h-3.5 w-3.5 text-primary inline" />
                    ) : (
                      <span className="text-muted-foreground/40">—</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </EvaLayout>
  );
}
