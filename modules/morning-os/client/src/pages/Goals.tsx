import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import type { Goal } from '@shared/schema';
import { HORIZONS } from '@/lib/eva';
import { EvaLayout } from '@/components/EvaLayout';
import { apiRequest } from '@/lib/queryClient';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/use-toast';
import { Check } from 'lucide-react';

export default function GoalsPage() {
  const goalsQ = useQuery<Goal[]>({ queryKey: ['/api/goals'] });
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [draft, setDraft] = useState<Record<string, string>>({});

  useEffect(() => {
    if (goalsQ.data) {
      const next: Record<string, string> = {};
      goalsQ.data.forEach((g) => (next[g.horizon] = g.content));
      setDraft(next);
    }
  }, [goalsQ.data]);

  const saveMut = useMutation({
    mutationFn: async (payload: { horizon: string; content: string }) => {
      const r = await apiRequest('POST', '/api/goals', payload);
      return r.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/api/goals'] });
      toast({ description: 'Goal updated.' });
    },
  });

  return (
    <EvaLayout>
      <div className="max-w-3xl mx-auto px-6 md:px-10 py-10 md:py-16 eva-fade-in">
        <div className="mb-12">
          <div className="text-[11px] uppercase tracking-[0.18em] text-primary/80 mb-3">
            Goals
          </div>
          <h1
            className="font-medium leading-tight"
            style={{ fontSize: 'clamp(1.6rem, 3.2vw, 2.1rem)' }}
          >
            What you are building, across time.
          </h1>
          <p className="text-muted-foreground mt-3 text-sm max-w-xl">
            Set the horizons. Update anytime. These are what the morning ritual
            ladders up to.
          </p>
        </div>

        <div className="space-y-10">
          {HORIZONS.map((h) => {
            const original = goalsQ.data?.find((g) => g.horizon === h.key)?.content ?? '';
            const value = draft[h.key] ?? '';
            const changed = value !== original;
            const isLife = h.key === 'life';
            return (
              <div key={h.key} className="space-y-3" data-testid={`section-goal-${h.key}`}>
                <div className="flex items-baseline justify-between">
                  <label className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                    {h.label}
                  </label>
                  {changed && (
                    <Button
                      size="sm"
                      onClick={() =>
                        saveMut.mutate({ horizon: h.key, content: value })
                      }
                      disabled={saveMut.isPending}
                      className="bg-primary text-primary-foreground hover:bg-primary/90 h-8"
                      data-testid={`button-save-${h.key}`}
                    >
                      <Check className="h-3.5 w-3.5 mr-1.5" />
                      Save
                    </Button>
                  )}
                </div>
                {isLife ? (
                  <Textarea
                    rows={4}
                    value={value}
                    onChange={(e) =>
                      setDraft((d) => ({ ...d, [h.key]: e.target.value }))
                    }
                    placeholder="The life you are designing…"
                    className="bg-card border-card-border text-base eva-accent placeholder:text-muted-foreground/60 placeholder:not-italic"
                    style={{ fontWeight: isLife ? 500 : 400 }}
                    data-testid={`input-goal-${h.key}`}
                  />
                ) : (
                  <Input
                    value={value}
                    onChange={(e) =>
                      setDraft((d) => ({ ...d, [h.key]: e.target.value }))
                    }
                    placeholder={`Goal for ${h.label.toLowerCase()}…`}
                    className="bg-card border-card-border h-12 text-base"
                    data-testid={`input-goal-${h.key}`}
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>
    </EvaLayout>
  );
}
