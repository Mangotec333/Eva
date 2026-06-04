import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { XCircle, RefreshCw, AlertTriangle } from "lucide-react";
import { apiRequest } from "@/lib/queryClient";
import type { AgentTask } from "@shared/schema";

const STATUS_COLOR: Record<string, string> = {
  running: "text-cyan-400 dot-pulse", completed: "text-green-400",
  stalled: "text-orange-400", killed: "text-red-400", manual: "text-slate-400",
};
const TIER_COLOR: Record<string, string> = {
  low: "text-green-400", medium: "text-yellow-400", high: "text-red-400",
};

const ADMIN_PIN = "557799";

export default function AdminOps() {
  const qc = useQueryClient();

  const { data: tasks = [], isLoading, refetch } = useQuery<AgentTask[]>({
    queryKey: ["/api/admin/agent-tasks"],
    queryFn: () => fetch("/api/admin/agent-tasks", { headers: { "x-admin-pin": ADMIN_PIN } }).then(r => r.json()),
    refetchInterval: 30000,
  });

  const watchdogMutation = useMutation({
    mutationFn: () => fetch("/api/admin/watchdog", { method: "POST", headers: { "x-admin-pin": ADMIN_PIN } }).then(r => r.json()),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["/api/admin/agent-tasks"] });
    },
  });

  const killMutation = useMutation({
    mutationFn: (id: number) => fetch(`/api/admin/agent-tasks/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", "x-admin-pin": ADMIN_PIN },
      body: JSON.stringify({ status: "killed", result: "Manually killed by admin" }),
    }).then(r => r.json()),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["/api/admin/agent-tasks"] }),
  });

  const running = tasks.filter(t => t.status === "running");
  const stalled = tasks.filter(t => t.status === "stalled");
  const recent = tasks.filter(t => !["running", "stalled"].includes(t.status)).slice(0, 15);

  const formatTime = (ts: string) => new Date(ts).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  const formatDuration = (start: string) => {
    const min = Math.round((Date.now() - new Date(start).getTime()) / 60000);
    return min < 60 ? `${min}m` : `${Math.round(min / 60)}h`;
  };

  return (
    <div className="px-8 py-8 max-w-3xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-base font-semibold text-foreground">Operations</h1>
          <p className="text-xs text-muted-foreground mt-0.5 mono">Agent tasks · watchdog · kill switch</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => refetch()}
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground border border-border px-3 py-1.5 rounded-lg transition-colors">
            <RefreshCw size={12} /> Refresh
          </button>
          <button onClick={() => watchdogMutation.mutate()}
            disabled={watchdogMutation.isPending}
            data-testid="btn-run-watchdog"
            className="flex items-center gap-1.5 text-xs text-amber-400 border border-amber-400/30 bg-amber-400/5 hover:bg-amber-400/10 px-3 py-1.5 rounded-lg transition-colors">
            <AlertTriangle size={12} /> Run Watchdog
          </button>
        </div>
      </div>

      {/* Watchdog result */}
      {watchdogMutation.isSuccess && (
        <div className="bg-amber-400/5 border border-amber-400/20 rounded-xl px-4 py-3 mb-6 text-xs text-amber-400">
          Watchdog ran — {(watchdogMutation.data as any)?.stalled ?? 0} task(s) flagged as stalled
        </div>
      )}

      {/* Running */}
      {running.length > 0 && (
        <div className="mb-6">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium mb-3">Running ({running.length})</div>
          <div className="space-y-2">
            {running.map(t => (
              <TaskRow key={t.id} task={t} onKill={() => killMutation.mutate(t.id)}
                formatTime={formatTime} formatDuration={formatDuration} showKill />
            ))}
          </div>
        </div>
      )}

      {/* Stalled */}
      {stalled.length > 0 && (
        <div className="mb-6">
          <div className="text-[10px] uppercase tracking-wide text-orange-400 font-medium mb-3">⚠ Stalled ({stalled.length})</div>
          <div className="space-y-2">
            {stalled.map(t => (
              <TaskRow key={t.id} task={t} onKill={() => killMutation.mutate(t.id)}
                formatTime={formatTime} formatDuration={formatDuration} showKill />
            ))}
          </div>
        </div>
      )}

      {/* Recent */}
      {recent.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium mb-3">Recent</div>
          <div className="space-y-1.5">
            {recent.map(t => (
              <TaskRow key={t.id} task={t} onKill={() => {}}
                formatTime={formatTime} formatDuration={formatDuration} showKill={false} />
            ))}
          </div>
        </div>
      )}

      {!isLoading && tasks.length === 0 && (
        <div className="text-sm text-muted-foreground text-center py-12">No agent tasks logged yet.</div>
      )}
    </div>
  );
}

function TaskRow({ task, onKill, formatTime, formatDuration, showKill }: any) {
  return (
    <div data-testid={`agent-task-${task.id}`}
      className="bg-card border border-border rounded-xl px-4 py-3 flex items-center gap-3">
      <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
        task.status === "running" ? "bg-cyan-400 dot-pulse" :
        task.status === "stalled" ? "bg-orange-400" :
        task.status === "completed" ? "bg-green-400" : "bg-red-400"
      }`} />
      <div className="flex-1 min-w-0">
        <div className="text-sm text-foreground">{task.taskName}</div>
        <div className="flex items-center gap-3 mt-0.5">
          <span className="text-[10px] text-muted-foreground mono">{task.taskType}</span>
          <span className={`text-[10px] font-medium ${TIER_COLOR[task.costTier] || "text-slate-400"}`}>
            {task.costTier} cost
          </span>
          <span className={`text-[10px] ${STATUS_COLOR[task.status] || "text-slate-400"}`}>{task.status}</span>
          <span className="text-[10px] text-muted-foreground mono">{formatTime(task.startedAt)}</span>
          {task.status === "running" && (
            <span className="text-[10px] text-muted-foreground mono">{formatDuration(task.startedAt)} elapsed</span>
          )}
        </div>
        {task.result && (
          <div className="text-[10px] text-muted-foreground mt-1 truncate">{task.result}</div>
        )}
      </div>
      {showKill && (
        <button onClick={onKill}
          className="text-muted-foreground hover:text-red-400 transition-colors flex-shrink-0">
          <XCircle size={15} />
        </button>
      )}
    </div>
  );
}
