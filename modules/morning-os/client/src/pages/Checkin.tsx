import { useState } from 'react';
import { useLocation } from 'wouter';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '@/lib/queryClient';
import {
  ENERGY_OPTIONS,
  WEEK_STATUS_OPTIONS,
  energyLabel,
  todayLocalISO,
  type EnergyValue,
  type WeekStatus,
} from '@/lib/eva';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { ArrowLeft, ArrowRight, Check } from 'lucide-react';
import { EvaLogo } from '@/components/EvaLogo';

const TOTAL_STEPS = 6;

export default function Checkin() {
  const [, navigate] = useLocation();
  const queryClient = useQueryClient();
  const [step, setStep] = useState(1);
  const [energy, setEnergy] = useState<EnergyValue | null>(null);
  const [goals, setGoals] = useState<string[]>(['', '', '']);
  const [weekStatus, setWeekStatus] = useState<WeekStatus | null>(null);
  const [weekGoal, setWeekGoal] = useState('');
  const [priority, setPriority] = useState('');
  const [constraint, setConstraint] = useState('');

  const save = useMutation({
    mutationFn: async () => {
      const r = await apiRequest('POST', '/api/checkins', {
        date: todayLocalISO(),
        energy,
        goals: JSON.stringify(goals.filter((g) => g.trim().length > 0)),
        weekStatus,
        weekGoal: weekGoal || null,
        priority,
        constraint: constraint || null,
      });
      return r.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/api/checkins'] });
      queryClient.invalidateQueries({ queryKey: ['/api/checkins/today'] });
      navigate('/');
    },
  });

  const canAdvance = (): boolean => {
    if (step === 1) return energy != null;
    if (step === 2) return goals.some((g) => g.trim().length > 0);
    if (step === 3) {
      if (!weekStatus) return false;
      if ((weekStatus === 'off_track' || weekStatus === 'unset') && !weekGoal.trim())
        return false;
      return true;
    }
    if (step === 4) return priority.trim().length > 0;
    if (step === 5) return true; // optional
    return true;
  };

  const next = () => {
    if (!canAdvance()) return;
    if (step === TOTAL_STEPS) {
      save.mutate();
      return;
    }
    setStep((s) => s + 1);
  };
  const back = () => setStep((s) => Math.max(1, s - 1));

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="px-6 md:px-10 py-5 border-b border-border flex items-center justify-between">
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
          data-testid="link-exit"
        >
          <EvaLogo className="h-5 w-5 text-primary" />
          <span>Exit</span>
        </button>
        <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
          Step {step} of {TOTAL_STEPS}
        </div>
      </header>

      {/* Progress */}
      <div className="px-6 md:px-10 pt-4">
        <div className="h-[2px] w-full bg-border overflow-hidden rounded-full">
          <div
            className="h-full bg-primary transition-all duration-500"
            style={{ width: `${(step / TOTAL_STEPS) * 100}%` }}
            data-testid="bar-progress"
          />
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 flex items-start md:items-center justify-center px-6 md:px-10 py-10 md:py-16">
        <div key={step} className="w-full max-w-2xl eva-fade-in">
          {step === 1 && (
            <StepEnergy value={energy} onChange={setEnergy} />
          )}
          {step === 2 && <StepGoals goals={goals} setGoals={setGoals} />}
          {step === 3 && (
            <StepWeek
              status={weekStatus}
              setStatus={setWeekStatus}
              weekGoal={weekGoal}
              setWeekGoal={setWeekGoal}
            />
          )}
          {step === 4 && <StepLeverage value={priority} onChange={setPriority} />}
          {step === 5 && (
            <StepConstraint value={constraint} onChange={setConstraint} />
          )}
          {step === 6 && (
            <StepSummary
              priority={priority}
              goals={goals.filter((g) => g.trim())}
              constraint={constraint}
              energy={energy}
            />
          )}
        </div>
      </div>

      {/* Footer nav */}
      <footer className="px-6 md:px-10 py-6 border-t border-border flex items-center justify-between gap-3">
        <Button
          variant="ghost"
          onClick={back}
          disabled={step === 1}
          data-testid="button-back"
          className="text-muted-foreground"
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back
        </Button>
        <Button
          onClick={next}
          disabled={!canAdvance() || save.isPending}
          data-testid="button-next"
          size="lg"
          className={cn(
            'bg-primary text-primary-foreground hover:bg-primary/90 px-6',
            step === TOTAL_STEPS && 'eva-glow px-8 py-6 text-base'
          )}
        >
          {step === TOTAL_STEPS ? (
            save.isPending ? (
              'Saving…'
            ) : (
              <>
                <Check className="h-4 w-4 mr-2" />
                Lock it in. Start the day.
              </>
            )
          ) : (
            <>
              Continue
              <ArrowRight className="h-4 w-4 ml-2" />
            </>
          )}
        </Button>
      </footer>
    </div>
  );
}

function StepHeading({
  eyebrow,
  children,
}: {
  eyebrow: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-[0.18em] text-primary/80 mb-3">
        {eyebrow}
      </div>
      <h2
        className="text-balance font-medium leading-tight"
        style={{ fontSize: 'clamp(1.6rem, 3.2vw, 2.1rem)', lineHeight: 1.15 }}
      >
        {children}
      </h2>
    </div>
  );
}

function StepEnergy({
  value,
  onChange,
}: {
  value: EnergyValue | null;
  onChange: (v: EnergyValue) => void;
}) {
  return (
    <div className="space-y-10">
      <StepHeading eyebrow="01 · Energy">
        How is your energy this morning?
      </StepHeading>
      <div className="grid grid-cols-2 gap-3">
        {ENERGY_OPTIONS.map((o) => {
          const active = value === o.value;
          return (
            <button
              key={o.value}
              type="button"
              onClick={() => onChange(o.value)}
              data-testid={`button-energy-${o.value}`}
              className={cn(
                'rounded-lg border bg-card p-5 text-left transition-all hover-elevate',
                active
                  ? 'border-primary ring-1 ring-primary/40'
                  : 'border-card-border'
              )}
            >
              <div className="text-2xl mb-2">{o.icon}</div>
              <div className="text-sm font-medium">{o.label}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function StepGoals({
  goals,
  setGoals,
}: {
  goals: string[];
  setGoals: (g: string[]) => void;
}) {
  return (
    <div className="space-y-10">
      <StepHeading eyebrow="02 · Today">
        What are the 3 most important things to accomplish today?
      </StepHeading>
      <div className="space-y-3">
        {goals.map((g, i) => (
          <div key={i} className="flex items-center gap-3">
            <span className="text-muted-foreground tabular-nums text-sm w-6">
              {(i + 1).toString().padStart(2, '0')}
            </span>
            <Input
              value={g}
              onChange={(e) => {
                const next = [...goals];
                next[i] = e.target.value;
                setGoals(next);
              }}
              placeholder={i === 0 ? 'The most important one…' : 'Add another…'}
              data-testid={`input-goal-${i}`}
              className="bg-card border-card-border h-12 text-base"
            />
          </div>
        ))}
        <p className="text-xs text-muted-foreground pt-2">At least one is required.</p>
      </div>
    </div>
  );
}

function StepWeek({
  status,
  setStatus,
  weekGoal,
  setWeekGoal,
}: {
  status: WeekStatus | null;
  setStatus: (v: WeekStatus) => void;
  weekGoal: string;
  setWeekGoal: (v: string) => void;
}) {
  const showGoalInput = status === 'off_track' || status === 'unset';
  return (
    <div className="space-y-10">
      <StepHeading eyebrow="03 · This Week">
        Are you on track for your weekly goals?
      </StepHeading>
      <div className="grid grid-cols-2 gap-3">
        {WEEK_STATUS_OPTIONS.map((o) => {
          const active = status === o.value;
          return (
            <button
              key={o.value}
              type="button"
              onClick={() => setStatus(o.value)}
              data-testid={`button-week-${o.value}`}
              className={cn(
                'rounded-lg border bg-card p-4 text-left text-sm font-medium hover-elevate',
                active
                  ? 'border-primary ring-1 ring-primary/40'
                  : 'border-card-border'
              )}
            >
              {o.label}
            </button>
          );
        })}
      </div>
      {showGoalInput && (
        <div className="space-y-2 eva-fade-in">
          <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
            What's the week's #1 goal?
          </div>
          <Input
            value={weekGoal}
            onChange={(e) => setWeekGoal(e.target.value)}
            placeholder="Name the single most important outcome…"
            data-testid="input-week-goal"
            className="bg-card border-card-border h-12 text-base"
          />
        </div>
      )}
    </div>
  );
}

function StepLeverage({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="space-y-10">
      <StepHeading eyebrow="04 · Leverage">
        Of everything on your plate — what is the ONE thing that, if done today, would make everything else easier or unnecessary?
      </StepHeading>
      <Textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="The single highest-leverage move…"
        data-testid="input-priority"
        rows={3}
        className="bg-card border-card-border text-lg eva-accent placeholder:text-muted-foreground/60 placeholder:not-italic"
        style={{ fontWeight: 500 }}
      />
    </div>
  );
}

function StepConstraint({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="space-y-10">
      <StepHeading eyebrow="05 · Constraint">
        What is most likely to steal your focus today?
      </StepHeading>
      <Textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Optional — name the threat so it has less power."
        data-testid="input-constraint"
        rows={3}
        className="bg-card border-card-border text-base"
      />
    </div>
  );
}

function StepSummary({
  priority,
  goals,
  constraint,
  energy,
}: {
  priority: string;
  goals: string[];
  constraint: string;
  energy: EnergyValue | null;
}) {
  return (
    <div className="space-y-10">
      <div>
        <div className="text-[11px] uppercase tracking-[0.18em] text-primary/80 mb-3">
          06 · EVA Insight
        </div>
        <h2
          className="font-medium leading-tight"
          style={{ fontSize: 'clamp(1.6rem, 3.2vw, 2.1rem)', lineHeight: 1.15 }}
        >
          Here's your day, Vineet:
        </h2>
      </div>

      <div className="rounded-xl border border-primary/30 bg-card p-6 md:p-8 eva-glow">
        <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground mb-2">
          Today's priority
        </div>
        <p
          className="eva-accent font-medium leading-tight text-balance"
          style={{ fontSize: 'clamp(1.4rem, 2.6vw, 1.85rem)' }}
          data-testid="text-summary-priority"
        >
          {priority}
        </p>
      </div>

      <div className="grid md:grid-cols-2 gap-6 text-sm">
        <div>
          <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground mb-2">
            Today's goals
          </div>
          <ul className="space-y-1.5">
            {goals.map((g, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-muted-foreground tabular-nums">
                  {(i + 1).toString().padStart(2, '0')}
                </span>
                <span>{g}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="space-y-4">
          <div>
            <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground mb-1.5">
              Watch out for
            </div>
            <div>{constraint || '—'}</div>
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground mb-1.5">
              Energy
            </div>
            <div>{energyLabel(energy)}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
