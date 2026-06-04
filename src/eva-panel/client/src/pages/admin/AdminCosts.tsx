import { useQuery, useMutation } from "@tanstack/react-query";
import { queryClient, apiRequest } from "@/lib/queryClient";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { AgentTask } from "@shared/schema";
import { Zap, AlertTriangle, CheckCircle2, XCircle, Clock, Skull } from "lucide-react";

type CostTier = "low" | "medium" | "high";
type TaskStatus = "running" | "completed" | "stalled" | "killed" | "approved" | "pending_approval";

const TIER_CONFIG: Record<CostTier, { label: string; color: string; bg: string }> = {
  low: { label: "Low", color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/20" },
  medium: { label: "Med", color: "text-amber-400", bg: "bg-amber-500/10 border-amber-500/20" },
  high: { label: "High", color: "text-red-400", bg: "bg-red-500/10 border-red-500/20" },
};

const STATUS_CONFIG: Record<TaskStatus, { icon: React.ReactNode; label: string; color: string }> = {
  running: { icon: <Clock className="w-3.5 h-3.5" />, label: "Running", color: "text-primary" },
  completed: { icon: <CheckCircle2 className="w-3.5 h-3.5" />, label: "Done", color: "text-emerald-400" },
  stalled: { icon: <AlertTriangle className="w-3.5 h-3.5" />, label: "Stalled", color: "text-amber-400" },
  killed: { icon: <Skull className="w-3.5 h-3.5" />, label: "Killed", color: "text-red-400" },
  approved: { icon: <CheckCircle2 className="w-3.5 h-3.5" />, label: "Approved", color: "text-emerald-400" },
  pending_approval: { icon: <AlertTriangle className="w-3.5 h-3.5" />, label: "Needs Approval", color: "text-amber-400" },
};

function fmtTime(t: string | null) {
  if (!t) return "—";
  try {
    return new Date(t).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return t;
  }
}

function elapsed(start: string, end: string | null) {
  try {
    const s = new Date(start).getTime();
    const e = end ? new Date(end).getTime() : Date.now();
    const m = Math.round((e - s) / 60000);
    return `${m}m`;
  } catch {
    return "—";
  }
}

function TierBadge({ tier }: { tier: string }) {
  const cfg = TIER_CONFIG[tier as CostTier] ?? TIER_CONFIG.medium;
  return (
    <Badge className={`text-xs ${cfg.bg} ${cfg.color} border px-2 py-0`}>{cfg.label}</Badge>
  );
}

function StatusChip({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status as TaskStatus];
  if (!cfg) return <Badge variant="outline" className="text-xs">{status}</Badge>;
  return (
    <span className={`flex items-center gap-1 text-xs ${cfg.color}`}>
      {cfg.icon}
      {cfg.label}
    </span>
  );
}

export default function AdminCosts() {
  const { data: tasks, isLoading } = useQuery<AgentTask[]>({
    queryKey: ["/api/admin/agent-tasks"],
    queryFn: () => apiRequest("GET", "/api/admin/agent-tasks").then(r => r.json()),
    refetchInterval: 10_000,
  });

  const killMutation = useMutation({
    mutationFn: (id: number) => apiRequest("POST", `/api/admin/agent-tasks/${id}/kill`, {}).then(r => r.json()),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["/api/admin/agent-tasks"] }),
  });

  const watchdogMutation = useMutation({
    mutationFn: () => apiRequest("POST", "/api/admin/watchdog", {}).then(r => r.json()),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["/api/admin/agent-tasks"] }),
  });

  const pendingApproval = (tasks ?? []).filter(t => t.status === "pending_approval");
  const running = (tasks ?? []).filter(t => t.status === "running");
  const stalled = (tasks ?? []).filter(t => t.status === "stalled");
  const highTier = (tasks ?? []).filter(t => t.costTier === "high");

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-base font-semibold text-foreground">Cost Gate</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Agent task log · watchdog · approval queue
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5 text-xs border-amber-500/30 text-amber-400 hover:bg-amber-500/10"
          onClick={() => watchdogMutation.mutate()}
          disabled={watchdogMutation.isPending}
          data-testid="button-run-watchdog"
        >
          <Zap className="w-3.5 h-3.5" />
          Run Watchdog
        </Button>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "Running", value: running.length, color: "text-primary" },
          { label: "Stalled", value: stalled.length, color: "text-amber-400" },
          { label: "High Cost", value: highTier.length, color: "text-red-400" },
          { label: "Needs Approval", value: pendingApproval.length, color: "text-amber-400" },
        ].map(stat => (
          <Card key={stat.label} className="eva-card bg-card border-border">
            <CardContent className="p-3">
              <p className="text-xs text-muted-foreground">{stat.label}</p>
              <p className={`text-xl font-semibold mt-1 ${stat.color}`}>{stat.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Pending approval queue */}
      {pendingApproval.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-amber-400 uppercase tracking-wider">Approval Queue</p>
          {pendingApproval.map(task => (
            <Card key={task.id} className="eva-card bg-amber-500/5 border-amber-500/20">
              <CardContent className="p-4 flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-medium text-foreground">{task.taskName}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">{task.taskType} · est. {task.estimatedMinutes ?? "?"}m</p>
                </div>
                <div className="flex items-center gap-2">
                  <TierBadge tier={task.costTier} />
                  <Button
                    size="sm"
                    className="h-7 text-xs bg-primary text-primary-foreground hover:bg-primary/90"
                    data-testid={`button-approve-task-${task.id}`}
                  >
                    Approve
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs text-red-400 hover:text-red-300"
                    onClick={() => killMutation.mutate(task.id)}
                    disabled={killMutation.isPending}
                    data-testid={`button-kill-task-${task.id}`}
                  >
                    Kill
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Full task log */}
      <div className="space-y-2">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Task Log</p>

        {isLoading ? (
          <div className="space-y-2">
            {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-16 w-full rounded-lg" />)}
          </div>
        ) : (tasks ?? []).length === 0 ? (
          <div className="text-center py-12 text-muted-foreground text-sm">
            No agent tasks recorded yet.
          </div>
        ) : (
          <div className="space-y-2">
            {(tasks ?? []).slice().reverse().map(task => (
              <Card
                key={task.id}
                className={`eva-card border-border ${task.status === "stalled" ? "bg-amber-500/5 border-amber-500/20" : "bg-card"}`}
                data-testid={`card-task-${task.id}`}
              >
                <CardContent className="p-3 flex items-center gap-4">
                  {/* Status icon */}
                  <div className="flex-shrink-0">
                    <StatusChip status={task.status} />
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">{task.taskName}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {task.taskType}
                      {task.subagentId && <span className="ml-2 font-mono opacity-60">{task.subagentId.slice(0, 8)}</span>}
                    </p>
                  </div>

                  {/* Tier */}
                  <TierBadge tier={task.costTier} />

                  {/* Time */}
                  <div className="text-right flex-shrink-0">
                    <p className="text-xs text-muted-foreground">{fmtTime(task.startedAt)}</p>
                    <p className="text-xs text-muted-foreground">
                      {elapsed(task.startedAt, task.completedAt ?? task.killedAt ?? task.stalledAt)}
                    </p>
                  </div>

                  {/* Kill button for running/stalled */}
                  {(task.status === "running" || task.status === "stalled") && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 text-xs text-red-400 hover:text-red-300 flex-shrink-0"
                      onClick={() => killMutation.mutate(task.id)}
                      disabled={killMutation.isPending}
                      data-testid={`button-kill-running-${task.id}`}
                    >
                      <XCircle className="w-3.5 h-3.5" />
                    </Button>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
