import { Plus } from "lucide-react";
import type { Activity } from "@shared/schema";
import TaskCard from "./TaskCard";

interface KanbanColumnProps {
  title: string;
  status: string;
  activities: Activity[];
  accent: string;
  icon: string;
  onAddTask: (status: string) => void;
  onEditTask: (activity: Activity) => void;
}

export default function KanbanColumn({
  title, status, activities, accent, icon, onAddTask, onEditTask,
}: KanbanColumnProps) {
  return (
    <div className="flex flex-col min-w-0">
      {/* Column header */}
      <div className="flex items-center justify-between px-1 mb-3">
        <div className="flex items-center gap-2">
          <span className="text-base">{icon}</span>
          <span className="text-sm font-semibold text-foreground">{title}</span>
          <span
            className="text-xs font-mono px-1.5 py-0.5 rounded-full min-w-[22px] text-center"
            style={{ background: `${accent}22`, color: accent }}
          >
            {activities.length}
          </span>
        </div>
        <button
          data-testid={`button-add-${status}`}
          className="w-6 h-6 rounded flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          onClick={() => onAddTask(status)}
          title={`Add to ${title}`}
        >
          <Plus size={14} />
        </button>
      </div>

      {/* Column accent line */}
      <div className="h-0.5 rounded-full mb-3" style={{ background: `linear-gradient(to right, ${accent}60, transparent)` }} />

      {/* Cards */}
      <div className="kanban-col space-y-2 pr-0.5">
        {activities.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-muted-foreground/40 text-xs gap-1">
            <span className="text-xl opacity-30">{icon}</span>
            <span>Empty</span>
          </div>
        ) : (
          activities.map(activity => (
            <TaskCard
              key={activity.id}
              activity={activity}
              onEdit={onEditTask}
            />
          ))
        )}
      </div>
    </div>
  );
}
