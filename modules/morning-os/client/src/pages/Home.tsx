import { useQuery } from '@tanstack/react-query';
import { Link } from 'wouter';
import { useEffect, useState } from 'react';
import type { Checkin } from '@shared/schema';
import {
  computeStreak,
  energyLabel,
  formatLongDate,
  parseGoals,
} from '@/lib/eva';
import { Button } from '@/components/ui/button';
import { EvaLayout } from '@/components/EvaLayout';
import { ArrowRight, Clock, Flame, Target } from 'lucide-react';

type ActivityResp =
  | { available: true; data: any }
  | { available: false; reason: string };

function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);
  return now;
}

function Greeting() {
  const hour = new Date().getHours();
  if (hour < 5) return 'Still up';
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

export default function Home() {
  const now = useClock();
  const todayQ = useQuery<Checkin | null>({ queryKey: ['/api/checkins/today'] });
  const allQ = useQuery<Checkin[]>({ queryKey: ['/api/checkins'] });
  const actQ = useQuery<ActivityResp>({ queryKey: ['/api/activity/today'] });

  const today = todayQ.data;
  const streak = computeStreak(allQ.data ?? []);
  const yesterdayCheckin = (allQ.data ?? []).find((c) => {
    const d = new Date();
    d.setDate(d.getDate() - 1);
    return c.date === d.toISOString().slice(0, 10);
  });

  return (
    <EvaLayout>
      <div className="max-w-4xl mx-auto px-6 md:px-10 py-10 md:py-16 eva-fade-in">
        {/* Header */}
        <div className="flex items-baseline justify-between flex-wrap gap-2">
          <div>
            <h1 className="text-xl font-medium tracking-tight" data-testid="text-greeting">
              {Greeting()}, Vineet.
            </h1>
            <p className="text-sm text-muted-foreground mt-1" data-testid="text-date">
              {formatLongDate(now)} ·{' '}
              {now.toLocaleTimeString('en-US', {
                hour: 'numeric',
                minute: '2-digit',
              })}
            </p>
          </div>
        </div>

        {/* Headline question */}
        <h2
          className="mt-14 md:mt-20 text-xl md:text-xl font-medium text-balance leading-tight eva-accent"
          style={{ fontSize: '2rem', lineHeight: 1.15 }}
          data-testid="text-headline"
        >
          What needs your attention today?
        </h2>

        {/* CTA */}
        <div className="mt-8">
          <Link href="/checkin">
            <a data-testid="link-start-checkin">
              <Button
                size="lg"
                className="bg-primary text-primary-foreground hover:bg-primary/90 px-6 py-6 text-base eva-glow"
              >
                {today ? 'Review today' : 'Start morning check-in'}
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </a>
          </Link>
        </div>

        {/* Three cards */}
        <div className="mt-14 grid gap-4 md:grid-cols-3">
          <Card
            label="Today's priority"
            icon={<Target className="h-4 w-4" />}
            empty={!today}
            emptyHint="Complete check-in to set"
            testId="card-today-priority"
          >
            {today && (
              <p className="text-base eva-accent font-medium leading-snug">
                {today.priority}
              </p>
            )}
          </Card>

          <Card
            label="Yesterday's focus"
            icon={<Clock className="h-4 w-4" />}
            empty={!yesterdayCheckin && !actQ.data?.available}
            emptyHint={
              actQ.data && !actQ.data.available
                ? 'Logger not running'
                : 'No check-in yesterday'
            }
            testId="card-yesterday"
          >
            {yesterdayCheckin ? (
              <p className="text-sm text-foreground/90 leading-snug">
                {yesterdayCheckin.priority}
              </p>
            ) : actQ.data?.available ? (
              <ActivityYesterday data={actQ.data.data} />
            ) : null}
          </Card>

          <Card
            label="Current streak"
            icon={<Flame className="h-4 w-4" />}
            empty={streak === 0}
            emptyHint="Start your streak today"
            testId="card-streak"
          >
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-medium tabular-nums" data-testid="text-streak">
                {streak}
              </span>
              <span className="text-sm text-muted-foreground">
                {streak === 1 ? 'day' : 'days'}
              </span>
            </div>
          </Card>
        </div>

        {/* Today summary inline */}
        {today && (
          <div className="mt-14 border-t border-border pt-10">
            <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground mb-3">
              Locked in for today
            </div>
            <div className="grid md:grid-cols-2 gap-x-10 gap-y-4 text-sm">
              <Row label="Energy">{energyLabel(today.energy)}</Row>
              <Row label="Watch out for">{today.constraint || '—'}</Row>
              <Row label="Goals" full>
                <ul className="space-y-1.5">
                  {parseGoals(today).map((g, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="text-muted-foreground tabular-nums">
                        {(i + 1).toString().padStart(2, '0')}
                      </span>
                      <span>{g}</span>
                    </li>
                  ))}
                </ul>
              </Row>
            </div>
          </div>
        )}
      </div>
    </EvaLayout>
  );
}

function Card({
  label,
  icon,
  children,
  empty,
  emptyHint,
  testId,
}: {
  label: string;
  icon: React.ReactNode;
  children?: React.ReactNode;
  empty?: boolean;
  emptyHint?: string;
  testId?: string;
}) {
  return (
    <div
      data-testid={testId}
      className="rounded-lg border border-card-border bg-card p-5 min-h-[140px] flex flex-col"
    >
      <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
        <span className="text-primary">{icon}</span>
        {label}
      </div>
      <div className="mt-4 flex-1 flex items-start">
        {empty ? (
          <p className="text-sm text-muted-foreground italic">{emptyHint}</p>
        ) : (
          children
        )}
      </div>
    </div>
  );
}

function Row({
  label,
  children,
  full,
}: {
  label: string;
  children: React.ReactNode;
  full?: boolean;
}) {
  return (
    <div className={full ? 'md:col-span-2' : undefined}>
      <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground mb-1.5">
        {label}
      </div>
      <div className="text-foreground">{children}</div>
    </div>
  );
}

function ActivityYesterday({ data }: { data: any }) {
  const topApps: any[] = data?.top_apps ?? data?.topApps ?? [];
  const focus = data?.focus_score ?? data?.focusScore;
  return (
    <div className="text-sm space-y-1">
      {focus != null && (
        <div>
          <span className="text-muted-foreground">Focus: </span>
          <span>{focus}</span>
        </div>
      )}
      {topApps.length > 0 && (
        <div className="text-muted-foreground truncate">
          {topApps
            .slice(0, 3)
            .map((a: any) => a?.name ?? a?.app ?? a)
            .join(' · ')}
        </div>
      )}
    </div>
  );
}
