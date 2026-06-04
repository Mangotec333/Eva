import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Zap, CheckCircle2, ArrowRight } from "lucide-react";
import { apiRequest } from "@/lib/queryClient";
import type { Activity, EnergyLog } from "@shared/schema";

const ENERGY_COLORS = ["", "#ef4444", "#f97316", "#eab308", "#22c55e", "#22d3ee"];
const ENERGY_LABELS = ["", "Drained", "Low", "Okay", "Good", "Charged"];

function EnergyRow() {
  const qc = useQueryClient();
  const { data: todayLogs = [] } = useQuery<EnergyLog[]>({ queryKey: ["/api/energy/today"] });
  const logMutation = useMutation({
    mutationFn: (level: number) => {
      const h = new Date().getHours();
      const period = h < 12 ? "morning" : h < 17 ? "midday" : "evening";
      return apiRequest("POST", "/api/energy", { level, period });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["/api/energy/today"] }),
  });
  const latest = [...todayLogs].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())[0];

  return (
    <div className="flex items-center gap-3">
      <Zap size={14} className="text-yellow-400 flex-shrink-0" />
      <span className="text-sm text-muted-foreground">Energy</span>
      {latest && (
        <span className="mono text-sm font-semibold" style={{ color: ENERGY_COLORS[latest.level] }}>
          {latest.level}/5 · {ENERGY_LABELS[latest.level]}
        </span>
      )}
      <div className="flex items-center gap-1 ml-2">
        {[1,2,3,4,5].map(n => (
          <button key={n}
            data-testid={`btn-energy-${n}`}
            onClick={() => logMutation.mutate(n)}
            disabled={logMutation.isPending}
            className="w-7 h-7 rounded text-xs font-bold border transition-all hover:scale-105"
            style={{ borderColor: ENERGY_COLORS[n] + "55", color: ENERGY_COLORS[n], background: latest?.level === n ? ENERGY_COLORS[n] + "22" : "transparent" }}>
            {n}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const qc = useQueryClient();
  const { data: activities = [] } = useQuery<Activity[]>({ queryKey: ["/api/activities"] });
  const { data: stats } = useQuery<any>({ queryKey: ["/api/stats"] });

  const inProgress = activities.filter(a => a.status === "in_progress")
    .sort((a, b) => {
      const p = { critical: 0, high: 1, medium: 2, low: 3 };
      return (p[a.priority as keyof typeof p] ?? 2) - (p[b.priority as keyof typeof p] ?? 2);
    }).slice(0, 5);

  const doneMutation = useMutation({
    mutationFn: (id: number) => apiRequest("POST", `/api/activities/${id}/done`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["/api/activities"] }); qc.invalidateQueries({ queryKey: ["/api/stats"] }); },
  });

  const completionRate = stats ? Math.round((stats.tasks_completed / Math.max(stats.tasks_total, 1)) * 100) : 0;

  return (
    <div className="px-8 py-8 max-w-2xl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-foreground">Good afternoon, Vineet</h1>
        <p className="text-sm text-muted-foreground mt-1 mono">$10K by June 25 · One Man Army</p>
      </div>

      {/* Energy */}
      <div className="bg-card border border-border rounded-xl px-5 py-4 mb-6">
        <EnergyRow />
      </div>

      {/* Progress bar */}
      {stats && (
        <div className="bg-card border border-border rounded-xl px-5 py-4 mb-6">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm text-muted-foreground">Today's progress</span>
            <span className="mono text-sm font-semibold text-foreground">{completionRate}%</span>
          </div>
          <div className="h-1.5 rounded-full bg-muted overflow-hidden">
            <div className="h-full rounded-full bg-gradient-to-r from-primary to-green-400 transition-all duration-500"
              style={{ width: `${completionRate}%` }} />
          </div>
          <div className="flex items-center gap-6 mt-3">
            {[
              { label: "In Progress", val: stats.tasks_in_progress, color: "text-cyan-400" },
              { label: "Done", val: stats.tasks_completed, color: "text-green-400" },
              { label: "Planned", val: stats.tasks_planned, color: "text-indigo-400" },
              { label: "Deals Active", val: stats.deals_active, color: "text-orange-400" },
            ].map(({ label, val, color }) => (
              <div key={label} className="text-center">
                <div className={`text-base font-semibold mono ${color}`}>{val}</div>
                <div className="text-[10px] text-muted-foreground mt-0.5">{label}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Top priorities */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-foreground">In Progress</h2>
          <a href="/#/board" className="text-xs text-muted-foreground hover:text-primary flex items-center gap-1 transition-colors">
            Full board <ArrowRight size={11} />
          </a>
        </div>
        <div className="space-y-2">
          {inProgress.length === 0 && (
            <div className="text-sm text-muted-foreground py-4 text-center">Nothing in progress. Add a task.</div>
          )}
          {inProgress.map(task => (
            <div key={task.id} data-testid={`task-row-${task.id}`}
              className="eva-card bg-card border border-border rounded-xl px-4 py-3 flex items-start gap-3">
              <div className={`w-1 h-1 rounded-full mt-2 flex-shrink-0 ${
                task.priority === "critical" ? "bg-red-400" :
                task.priority === "high" ? "bg-orange-400" : "bg-yellow-400"
              }`} />
              <div className="flex-1 min-w-0">
                <div className="text-sm text-foreground font-medium leading-snug">{task.title}</div>
                {task.description && (
                  <div className="text-xs text-muted-foreground mt-0.5 line-clamp-1">{task.description}</div>
                )}
              </div>
              <button
                data-testid={`btn-done-${task.id}`}
                onClick={() => doneMutation.mutate(task.id)}
                disabled={doneMutation.isPending}
                className="flex-shrink-0 w-7 h-7 rounded-lg border border-border text-muted-foreground hover:text-green-400 hover:border-green-400/40 transition-colors flex items-center justify-center"
              >
                <CheckCircle2 size={14} />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
