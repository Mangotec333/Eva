import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Zap, TrendingUp } from "lucide-react";
import { apiRequest } from "@/lib/queryClient";
import type { EnergyLog } from "@shared/schema";

const ENERGY_COLORS = ["", "#ef4444", "#f97316", "#eab308", "#22c55e", "#22d3ee"];
const ENERGY_LABELS = ["", "Drained", "Low", "Okay", "Good", "Charged"];
const PERIOD_ICONS: Record<string, string> = { morning: "☀️", midday: "⚡", evening: "🌙" };
const PERIOD_LABELS: Record<string, string> = { morning: "Morning", midday: "Midday", evening: "Evening" };

export default function EnergyPage() {
  const qc = useQueryClient();
  const [selectedPeriod, setSelectedPeriod] = useState<string>(() => {
    const h = new Date().getHours();
    if (h < 12) return "morning";
    if (h < 17) return "midday";
    return "evening";
  });
  const [note, setNote] = useState("");
  const [justLogged, setJustLogged] = useState<number | null>(null);

  const { data: todayLogs = [] } = useQuery<EnergyLog[]>({
    queryKey: ["/api/energy/today"],
  });

  const { data: recentLogs = [] } = useQuery<EnergyLog[]>({
    queryKey: ["/api/energy"],
  });

  const logMutation = useMutation({
    mutationFn: (level: number) =>
      apiRequest("POST", "/api/energy", { level, period: selectedPeriod, note: note || undefined }),
    onSuccess: (_, level) => {
      qc.invalidateQueries({ queryKey: ["/api/energy/today"] });
      qc.invalidateQueries({ queryKey: ["/api/energy"] });
      setJustLogged(level);
      setNote("");
      setTimeout(() => setJustLogged(null), 3000);
    },
  });

  const avgToday = todayLogs.length > 0
    ? (todayLogs.reduce((s, l) => s + l.level, 0) / todayLogs.length).toFixed(1)
    : null;

  const getPeriodLog = (period: string) =>
    todayLogs.filter(l => l.period === period).sort((a, b) =>
      new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    )[0];

  const formatTime = (ts: string) => {
    const d = new Date(ts);
    return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  };

  const formatDate = (ts: string) => {
    const d = new Date(ts);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };

  // Group recent logs by date
  const logsByDate = recentLogs.reduce((acc, log) => {
    const date = log.date || log.timestamp.split("T")[0];
    if (!acc[date]) acc[date] = [];
    acc[date].push(log);
    return acc;
  }, {} as Record<string, EnergyLog[]>);

  return (
    <div className="p-6 max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-lg font-semibold flex items-center gap-2">
            <Zap size={20} className="text-yellow-400" />
            Energy Log
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5 mono">Track daily energy · Every entry preserved for ML</p>
        </div>
        {avgToday && (
          <div className="text-right">
            <div className="text-xs text-muted-foreground mb-1">Today's Average</div>
            <div className="text-2xl font-bold mono" style={{ color: ENERGY_COLORS[Math.round(parseFloat(avgToday))] }}>
              {avgToday}<span className="text-sm text-muted-foreground">/5</span>
            </div>
          </div>
        )}
      </div>

      {/* Today's check-ins */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        {["morning", "midday", "evening"].map(period => {
          const log = getPeriodLog(period);
          return (
            <div
              key={period}
              data-testid={`card-period-${period}`}
              className={`rounded-xl border p-4 cursor-pointer transition-all ${
                selectedPeriod === period
                  ? "border-primary/50 bg-primary/5"
                  : "border-border bg-card hover:border-border/80"
              }`}
              onClick={() => setSelectedPeriod(period)}
            >
              <div className="text-2xl mb-2">{PERIOD_ICONS[period]}</div>
              <div className="text-sm font-medium text-foreground">{PERIOD_LABELS[period]}</div>
              {log ? (
                <div className="mt-2">
                  <div className="text-xl font-bold mono" style={{ color: ENERGY_COLORS[log.level] }}>
                    {log.level}/5
                  </div>
                  <div className="text-xs text-muted-foreground">{ENERGY_LABELS[log.level]}</div>
                  <div className="text-xs text-muted-foreground mono mt-1">{formatTime(log.timestamp)}</div>
                  {log.note && <div className="text-xs text-muted-foreground mt-1 italic">{log.note}</div>}
                </div>
              ) : (
                <div className="text-xs text-muted-foreground mt-2">Not logged</div>
              )}
            </div>
          );
        })}
      </div>

      {/* Log energy */}
      <div className="bg-card border border-border rounded-xl p-5 mb-8">
        <div className="text-sm font-medium mb-1">Log {PERIOD_LABELS[selectedPeriod]} Energy</div>
        <div className="text-xs text-muted-foreground mb-4">How are you feeling right now?</div>

        <div className="flex items-center gap-3 mb-4">
          {[1, 2, 3, 4, 5].map(level => (
            <button
              key={level}
              data-testid={`button-log-energy-${level}`}
              className="flex-1 rounded-lg border-2 py-3 text-center transition-all hover:scale-105"
              style={{
                borderColor: justLogged === level ? ENERGY_COLORS[level] : ENERGY_COLORS[level] + "44",
                background: justLogged === level ? ENERGY_COLORS[level] + "22" : "transparent",
              }}
              onClick={() => logMutation.mutate(level)}
              disabled={logMutation.isPending}
            >
              <div className="text-lg font-bold mono" style={{ color: ENERGY_COLORS[level] }}>{level}</div>
              <div className="text-xs text-muted-foreground">{ENERGY_LABELS[level]}</div>
            </button>
          ))}
        </div>

        <input
          type="text"
          placeholder="Optional note (e.g. 'after gym', 'need coffee')"
          value={note}
          onChange={e => setNote(e.target.value)}
          className="w-full bg-muted border border-border rounded-md px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          data-testid="input-energy-note"
          onKeyDown={e => {
            if (e.key === "Enter" && note && justLogged) logMutation.mutate(justLogged);
          }}
        />

        {justLogged && (
          <div className="mt-3 text-sm text-green-400">
            ✓ {selectedPeriod} energy logged: {justLogged}/5 — {ENERGY_LABELS[justLogged]}
          </div>
        )}
      </div>

      {/* History */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp size={16} className="text-muted-foreground" />
          <h2 className="text-sm font-medium">History</h2>
          <span className="text-xs text-muted-foreground mono">{recentLogs.length} entries · never deleted</span>
        </div>

        {Object.entries(logsByDate)
          .sort(([a], [b]) => b.localeCompare(a))
          .slice(0, 7)
          .map(([date, logs]) => {
            const avg = (logs.reduce((s, l) => s + l.level, 0) / logs.length).toFixed(1);
            return (
              <div key={date} className="mb-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium text-muted-foreground mono">{formatDate(date + "T00:00:00")}</span>
                  <span className="text-xs mono font-semibold" style={{ color: ENERGY_COLORS[Math.round(parseFloat(avg))] }}>
                    avg {avg}
                  </span>
                </div>
                <div className="flex gap-2 flex-wrap">
                  {logs.map(log => (
                    <div
                      key={log.id}
                      data-testid={`log-entry-${log.id}`}
                      className="flex items-center gap-2 bg-card border border-border rounded-lg px-3 py-1.5 text-xs"
                    >
                      <span>{PERIOD_ICONS[log.period]}</span>
                      <span className="font-bold mono" style={{ color: ENERGY_COLORS[log.level] }}>{log.level}</span>
                      <span className="text-muted-foreground">{formatTime(log.timestamp)}</span>
                      {log.note && <span className="text-muted-foreground italic">· {log.note}</span>}
                    </div>
                  ))}
                </div>
              </div>
            );
          })}

        {recentLogs.length === 0 && (
          <div className="text-center py-12 text-muted-foreground/40 text-sm">
            No energy logs yet. Rate your energy above to start tracking.
          </div>
        )}
      </div>
    </div>
  );
}
