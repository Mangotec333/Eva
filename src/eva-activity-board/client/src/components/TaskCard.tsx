import { useState } from "react";
import { CheckCircle2, Clock, Trash2, Edit3, ChevronDown } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Activity } from "@shared/schema";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";

const PRIORITY_COLORS: Record<string, string> = {
  critical: "bg-red-500/15 text-red-400 border-red-500/20",
  high: "bg-orange-500/15 text-orange-400 border-orange-500/20",
  medium: "bg-yellow-500/15 text-yellow-400 border-yellow-500/20",
  low: "bg-slate-500/15 text-slate-400 border-slate-500/20",
};

const CATEGORY_COLORS: Record<string, string> = {
  acquisition: "bg-purple-500/15 text-purple-400",
  revenue: "bg-green-500/15 text-green-400",
  eva_build: "bg-cyan-500/15 text-cyan-400",
  operations: "bg-blue-500/15 text-blue-400",
  outreach: "bg-pink-500/15 text-pink-400",
  general: "bg-slate-500/15 text-slate-400",
};

const STATUS_OPTIONS = [
  { value: "planned", label: "Planned" },
  { value: "in_progress", label: "In Progress" },
  { value: "completed", label: "Completed" },
  { value: "carry_over", label: "Carry Over" },
  { value: "parking_lot", label: "Parking Lot" },
];

interface TaskCardProps {
  activity: Activity;
  onEdit?: (activity: Activity) => void;
}

export default function TaskCard({ activity, onEdit }: TaskCardProps) {
  const { toast } = useToast();
  const qc = useQueryClient();
  const [showStatusMenu, setShowStatusMenu] = useState(false);

  const doneMutation = useMutation({
    mutationFn: () => apiRequest("POST", `/api/activities/${activity.id}/done`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["/api/activities"] });
      qc.invalidateQueries({ queryKey: ["/api/stats"] });
      toast({ title: "Done ✓", description: activity.title });
    },
  });

  const statusMutation = useMutation({
    mutationFn: (status: string) =>
      apiRequest("PATCH", `/api/activities/${activity.id}/status`, { status }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["/api/activities"] });
      qc.invalidateQueries({ queryKey: ["/api/stats"] });
      setShowStatusMenu(false);
    },
  });

  const archiveMutation = useMutation({
    mutationFn: () => apiRequest("DELETE", `/api/activities/${activity.id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["/api/activities"] });
      qc.invalidateQueries({ queryKey: ["/api/stats"] });
      toast({ title: "Archived", description: "Data preserved for ML" });
    },
  });

  const tags: string[] = (() => {
    try { return JSON.parse(activity.tags || "[]"); } catch { return []; }
  })();

  const isCompleted = activity.status === "completed";
  const isInProgress = activity.status === "in_progress";

  const formatDate = (ts: string) => {
    if (!ts) return null;
    const d = new Date(ts);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  };

  return (
    <div
      data-testid={`card-task-${activity.id}`}
      className={`task-card relative rounded-lg border p-3 bg-card ${isCompleted ? "opacity-60" : ""}`}
      style={{ borderColor: isInProgress ? "hsl(187 85% 43% / 0.3)" : undefined }}
    >
      {/* Priority bar */}
      <div className={`absolute left-0 top-0 bottom-0 w-0.5 rounded-l-lg ${
        activity.priority === "critical" ? "bg-red-500" :
        activity.priority === "high" ? "bg-orange-400" :
        activity.priority === "medium" ? "bg-yellow-400" : "bg-slate-600"
      }`} />

      <div className="pl-2">
        {/* Top row: category + priority badges */}
        <div className="flex items-center gap-1.5 mb-2 flex-wrap">
          <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${CATEGORY_COLORS[activity.category] || CATEGORY_COLORS.general}`}>
            {activity.category.replace("_", " ")}
          </span>
          <span className={`text-xs px-1.5 py-0.5 rounded border font-medium ${PRIORITY_COLORS[activity.priority] || PRIORITY_COLORS.medium}`}>
            {activity.priority}
          </span>
          {isInProgress && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-cyan-500/15 text-cyan-400 status-pulse">● live</span>
          )}
        </div>

        {/* Title */}
        <h3 className={`text-sm font-medium leading-snug mb-1 ${isCompleted ? "line-through text-muted-foreground" : "text-foreground"}`}>
          {activity.title}
        </h3>

        {/* Description */}
        {activity.description && (
          <p className="text-xs text-muted-foreground leading-relaxed mb-2 line-clamp-2">
            {activity.description}
          </p>
        )}

        {/* Tags */}
        {tags.length > 0 && (
          <div className="flex gap-1 flex-wrap mb-2">
            {tags.map(tag => (
              <span key={tag} className="text-xs px-1.5 py-0.5 rounded bg-accent text-muted-foreground">
                #{tag}
              </span>
            ))}
          </div>
        )}

        {/* Timestamp */}
        {activity.completedAt ? (
          <div className="flex items-center gap-1 text-xs text-green-400 mb-2 mono">
            <CheckCircle2 size={11} />
            {formatDate(activity.completedAt)}
          </div>
        ) : activity.createdAt ? (
          <div className="flex items-center gap-1 text-xs text-muted-foreground mb-2 mono">
            <Clock size={11} />
            {formatDate(activity.createdAt)}
          </div>
        ) : null}

        {/* Action row */}
        <div className="flex items-center gap-1.5 mt-2">
          {/* DONE button — primary CTA */}
          {!isCompleted && (
            <Button
              size="sm"
              data-testid={`button-done-${activity.id}`}
              className="h-7 px-3 text-xs bg-primary/20 text-primary border border-primary/30 hover:bg-primary hover:text-primary-foreground font-semibold"
              variant="outline"
              onClick={() => doneMutation.mutate()}
              disabled={doneMutation.isPending}
            >
              {doneMutation.isPending ? "..." : "✓ Done"}
            </Button>
          )}

          {/* Status change */}
          <div className="relative">
            <button
              data-testid={`button-status-${activity.id}`}
              className="h-7 px-2 text-xs rounded-md bg-accent text-muted-foreground hover:text-foreground border border-border flex items-center gap-1"
              onClick={() => setShowStatusMenu(s => !s)}
            >
              Move <ChevronDown size={10} />
            </button>
            {showStatusMenu && (
              <div className="absolute bottom-full left-0 mb-1 w-36 bg-card border border-border rounded-md shadow-lg z-50 py-1">
                {STATUS_OPTIONS.filter(s => s.value !== activity.status).map(opt => (
                  <button
                    key={opt.value}
                    className="w-full text-left px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-accent"
                    onClick={() => statusMutation.mutate(opt.value)}
                    disabled={statusMutation.isPending}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Edit */}
          <button
            data-testid={`button-edit-${activity.id}`}
            className="h-7 w-7 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-accent"
            onClick={() => onEdit?.(activity)}
          >
            <Edit3 size={13} />
          </button>

          {/* Archive (soft delete) */}
          <button
            data-testid={`button-archive-${activity.id}`}
            className="h-7 w-7 rounded-md flex items-center justify-center text-muted-foreground hover:text-red-400 hover:bg-red-500/10 ml-auto"
            onClick={() => {
              if (confirm("Archive this task? Data is preserved for ML.")) archiveMutation.mutate();
            }}
            disabled={archiveMutation.isPending}
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>
    </div>
  );
}
