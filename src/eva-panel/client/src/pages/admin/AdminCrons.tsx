import { useQuery, useMutation } from "@tanstack/react-query";
import { queryClient, apiRequest } from "@/lib/queryClient";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { CronJob } from "@shared/schema";
import { Clock, CheckCircle2, XCircle, PlayCircle, PauseCircle, RefreshCw } from "lucide-react";

function statusBadge(status: string | null) {
  if (!status) return <Badge variant="outline" className="text-xs text-muted-foreground">—</Badge>;
  if (status === "success") return <Badge className="text-xs bg-emerald-500/15 text-emerald-400 border-emerald-500/20">success</Badge>;
  if (status === "failed") return <Badge className="text-xs bg-red-500/15 text-red-400 border-red-500/20">failed</Badge>;
  return <Badge variant="outline" className="text-xs">{status}</Badge>;
}

function fmtTime(t: string | null) {
  if (!t) return "—";
  try {
    return new Date(t).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return t;
  }
}

export default function AdminCrons() {
  const { data: crons, isLoading } = useQuery<CronJob[]>({
    queryKey: ["/api/admin/crons"],
    queryFn: () => apiRequest("GET", "/api/admin/crons").then(r => r.json()),
    refetchInterval: 30_000,
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      apiRequest("PATCH", `/api/admin/crons/${id}`, { enabled }).then(r => r.json()),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["/api/admin/crons"] }),
  });

  const refreshMutation = useMutation({
    mutationFn: () => apiRequest("POST", "/api/admin/crons/refresh", {}).then(r => r.json()),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["/api/admin/crons"] }),
  });

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-base font-semibold text-foreground">Cron Jobs</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            {crons?.length ?? 0} registered · EVA scheduled agents
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5 text-xs border-border"
          onClick={() => refreshMutation.mutate()}
          disabled={refreshMutation.isPending}
          data-testid="button-refresh-crons"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshMutation.isPending ? "animate-spin" : ""}`} />
          Sync
        </Button>
      </div>

      {/* Cron cards */}
      {isLoading ? (
        <div className="space-y-3">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-lg" />
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          {(crons ?? []).map(cron => (
            <Card
              key={cron.id}
              className="eva-card bg-card border-border"
              data-testid={`card-cron-${cron.id}`}
            >
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-4">
                  {/* Left */}
                  <div className="flex items-start gap-3 min-w-0">
                    <div className={`mt-0.5 flex-shrink-0 ${cron.enabled ? "text-primary" : "text-muted-foreground"}`}>
                      <Clock className="w-4 h-4" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground truncate">{cron.name}</p>
                      <p className="text-xs text-muted-foreground mt-0.5 font-mono">{cron.schedule}</p>
                      {cron.scheduleHuman && (
                        <p className="text-xs text-muted-foreground">{cron.scheduleHuman}</p>
                      )}
                      <p className="text-xs text-muted-foreground mt-0.5 font-mono opacity-60">{cron.cronId}</p>
                    </div>
                  </div>

                  {/* Right */}
                  <div className="flex flex-col items-end gap-2 flex-shrink-0">
                    {/* Toggle */}
                    <Button
                      variant="ghost"
                      size="sm"
                      className={`h-7 px-2 gap-1.5 text-xs ${cron.enabled ? "text-emerald-400 hover:text-emerald-300" : "text-muted-foreground hover:text-foreground"}`}
                      onClick={() => toggleMutation.mutate({ id: cron.id, enabled: !cron.enabled })}
                      disabled={toggleMutation.isPending}
                      data-testid={`button-toggle-cron-${cron.id}`}
                    >
                      {cron.enabled
                        ? <><PlayCircle className="w-3.5 h-3.5" />Active</>
                        : <><PauseCircle className="w-3.5 h-3.5" />Paused</>
                      }
                    </Button>

                    {/* Last status */}
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs text-muted-foreground">last:</span>
                      {statusBadge(cron.lastStatus)}
                    </div>
                  </div>
                </div>

                {/* Run times row */}
                <div className="flex items-center gap-6 mt-3 pt-3 border-t border-border">
                  <div>
                    <p className="text-xs text-muted-foreground">Last run</p>
                    <p className="text-xs text-foreground mt-0.5">{fmtTime(cron.lastRun)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Next run</p>
                    <p className="text-xs text-foreground mt-0.5">{fmtTime(cron.nextRun)}</p>
                  </div>
                  <div className="ml-auto">
                    {cron.enabled
                      ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 dot-pulse" />
                      : <XCircle className="w-3.5 h-3.5 text-muted-foreground" />
                    }
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}

          {(crons ?? []).length === 0 && (
            <div className="text-center py-12 text-muted-foreground text-sm">
              No cron jobs registered yet.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
