import { useQuery } from "@tanstack/react-query";

interface Stats {
  total: number;
  planned: number;
  in_progress: number;
  completed: number;
  carry_over: number;
  parking_lot: number;
  archived: number;
}

export default function StatsBar() {
  const { data: stats } = useQuery<Stats>({ queryKey: ["/api/stats"] });
  if (!stats) return null;

  const completionRate = stats.total > 0
    ? Math.round((stats.completed / stats.total) * 100)
    : 0;

  const statItems = [
    { label: "In Progress", value: stats.in_progress, color: "text-cyan-400" },
    { label: "Planned", value: stats.planned, color: "text-indigo-400" },
    { label: "Completed", value: stats.completed, color: "text-green-400" },
    { label: "Carry Over", value: stats.carry_over, color: "text-orange-400" },
    { label: "Parking Lot", value: stats.parking_lot, color: "text-slate-400" },
    { label: "Done Rate", value: `${completionRate}%`, color: completionRate >= 50 ? "text-green-400" : "text-yellow-400" },
  ];

  return (
    <div className="flex items-center gap-6 px-6 py-2.5 border-b border-border/50 bg-muted/20 flex-shrink-0 overflow-x-auto">
      {statItems.map(({ label, value, color }) => (
        <div key={label} className="flex items-center gap-2 flex-shrink-0" data-testid={`stat-${label.toLowerCase().replace(/\s/g, "-")}`}>
          <span className="text-xs text-muted-foreground">{label}</span>
          <span className={`text-sm font-semibold mono ${color}`}>{value}</span>
        </div>
      ))}
      <div className="flex-1 min-w-[80px]">
        <div className="h-1 rounded-full bg-muted overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-green-400 energy-bar"
            style={{ width: `${completionRate}%` }}
          />
        </div>
      </div>
    </div>
  );
}
