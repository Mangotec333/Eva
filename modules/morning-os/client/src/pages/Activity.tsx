import { useQuery } from '@tanstack/react-query';
import { EvaLayout } from '@/components/EvaLayout';
import { Activity as ActivityIcon, ExternalLink } from 'lucide-react';

type ActivityResp =
  | { available: true; data: any }
  | { available: false; reason: string };

export default function ActivityPage() {
  const q = useQuery<ActivityResp>({ queryKey: ['/api/activity/today'] });
  const resp = q.data;
  const available = resp?.available === true;
  const data = available ? (resp as any).data : null;

  return (
    <EvaLayout>
      <div className="max-w-3xl mx-auto px-6 md:px-10 py-10 md:py-16 eva-fade-in">
        <div className="mb-10">
          <div className="text-[11px] uppercase tracking-[0.18em] text-primary/80 mb-3">
            Activity
          </div>
          <h1
            className="font-medium leading-tight"
            style={{ fontSize: 'clamp(1.6rem, 3.2vw, 2.1rem)' }}
          >
            Where your attention went.
          </h1>
        </div>

        {q.isLoading ? (
          <div className="h-32 rounded-lg border border-card-border bg-card animate-pulse" />
        ) : !available ? (
          <div className="border border-card-border rounded-lg bg-card p-8" data-testid="empty-activity">
            <div className="flex items-center gap-3 mb-3">
              <ActivityIcon className="h-5 w-5 text-muted-foreground" />
              <div className="text-sm font-medium">EVA Logger is offline</div>
            </div>
            <p className="text-muted-foreground text-sm mb-5 max-w-md">
              Start EVA Logger to see your activity patterns — top apps, focus
              score, and peak focus hour for the day.
            </p>
            <a
              href="https://github.com/vineetkravi/eva-activity-logger"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 text-sm text-primary hover:underline"
              data-testid="link-setup-logger"
            >
              Setup instructions
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </div>
        ) : (
          <ActivityView data={data} />
        )}
      </div>
    </EvaLayout>
  );
}

function ActivityView({ data }: { data: any }) {
  const topApps: any[] = data?.top_apps ?? data?.topApps ?? [];
  const focus = data?.focus_score ?? data?.focusScore;
  const peak = data?.peak_focus_hour ?? data?.peakFocusHour;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4">
        <Stat label="Focus score" value={focus ?? '—'} testId="stat-focus" />
        <Stat label="Peak focus hour" value={peak ?? '—'} testId="stat-peak" />
      </div>
      <div>
        <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground mb-3">
          Top apps
        </div>
        {topApps.length === 0 ? (
          <p className="text-muted-foreground text-sm">No app data yet today.</p>
        ) : (
          <ul className="space-y-2">
            {topApps.slice(0, 8).map((a: any, i: number) => {
              const name = a?.name ?? a?.app ?? String(a);
              const minutes = a?.minutes ?? a?.duration_minutes ?? null;
              return (
                <li
                  key={i}
                  className="flex items-baseline justify-between border-b border-card-border/60 pb-2"
                >
                  <div className="flex gap-3">
                    <span className="text-muted-foreground tabular-nums text-sm w-6">
                      {(i + 1).toString().padStart(2, '0')}
                    </span>
                    <span className="text-sm">{name}</span>
                  </div>
                  {minutes != null && (
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {minutes}m
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  testId,
}: {
  label: string;
  value: string | number;
  testId?: string;
}) {
  return (
    <div className="rounded-lg border border-card-border bg-card p-5" data-testid={testId}>
      <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground mb-3">
        {label}
      </div>
      <div className="text-2xl font-medium eva-accent tabular-nums">{value}</div>
    </div>
  );
}
