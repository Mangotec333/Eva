import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Zap } from "lucide-react";
import { apiRequest } from "@/lib/queryClient";
import type { EnergyLog } from "@shared/schema";

interface EnergyWidgetProps {
  compact?: boolean;
}

const ENERGY_COLORS = ["", "#ef4444", "#f97316", "#eab308", "#22c55e", "#22d3ee"];
const PERIOD_ICONS: Record<string, string> = { morning: "☀️", midday: "⚡", evening: "🌙" };

export default function EnergyWidget({ compact = false }: EnergyWidgetProps) {
  const qc = useQueryClient();
  const [selectedPeriod, setSelectedPeriod] = useState<string>(() => {
    const h = new Date().getHours();
    if (h < 12) return "morning";
    if (h < 17) return "midday";
    return "evening";
  });
  const [note, setNote] = useState("");
  const [loggedLevel, setLoggedLevel] = useState<number | null>(null);

  const { data: todayLogs = [] } = useQuery<EnergyLog[]>({
    queryKey: ["/api/energy/today"],
    refetchInterval: 60000,
  });

  const logMutation = useMutation({
    mutationFn: (level: number) =>
      apiRequest("POST", "/api/energy", { level, period: selectedPeriod, note: note || undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["/api/energy/today"] });
      qc.invalidateQueries({ queryKey: ["/api/energy"] });
      setNote("");
    },
  });

  const handleEnergyClick = (level: number) => {
    setLoggedLevel(level);
    logMutation.mutate(level);
  };

  // Get today's latest log for each period
  const getPeriodLog = (period: string) =>
    todayLogs.filter(l => l.period === period).sort((a, b) =>
      new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    )[0];

  const avgToday = todayLogs.length > 0
    ? (todayLogs.reduce((s, l) => s + l.level, 0) / todayLogs.length).toFixed(1)
    : null;

  if (compact) {
    return (
      <div className="flex items-center gap-4 px-6 py-2 border-b border-border/30 bg-muted/10 flex-shrink-0">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Zap size={12} className="text-yellow-400" />
          <span>Energy</span>
          {avgToday && (
            <span className="mono font-semibold" style={{ color: ENERGY_COLORS[Math.round(parseFloat(avgToday))] }}>
              {avgToday}/5
            </span>
          )}
        </div>

        <div className="flex items-center gap-1">
          {["morning", "midday", "evening"].map(period => {
            const log = getPeriodLog(period);
            return (
              <button
                key={period}
                data-testid={`button-period-${period}`}
                className={`text-xs px-2 py-1 rounded flex items-center gap-1 transition-colors ${
                  selectedPeriod === period
                    ? "bg-accent text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                }`}
                onClick={() => setSelectedPeriod(period)}
              >
                {PERIOD_ICONS[period]}
                {log && (
                  <span className="mono" style={{ color: ENERGY_COLORS[log.level] }}>
                    {log.level}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-1">
          {[1, 2, 3, 4, 5].map(level => (
            <button
              key={level}
              data-testid={`button-energy-${level}`}
              className="w-7 h-7 rounded-md text-xs font-bold border transition-all hover:scale-110"
              style={{
                background: loggedLevel === level ? ENERGY_COLORS[level] + "33" : "transparent",
                borderColor: ENERGY_COLORS[level] + "66",
                color: ENERGY_COLORS[level],
              }}
              onClick={() => handleEnergyClick(level)}
              disabled={logMutation.isPending}
            >
              {level}
            </button>
          ))}
        </div>

        {logMutation.isPending && (
          <span className="text-xs text-muted-foreground">Logging...</span>
        )}
        {logMutation.isSuccess && (
          <span className="text-xs text-green-400">✓ Logged</span>
        )}
      </div>
    );
  }

  return (
    <div className="p-6">
      <h2 className="text-base font-semibold mb-4 flex items-center gap-2">
        <Zap size={16} className="text-yellow-400" />
        Energy Log
      </h2>
      {/* full mode rendered in EnergyPage */}
    </div>
  );
}
