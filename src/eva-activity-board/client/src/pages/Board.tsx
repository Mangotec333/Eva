import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import KanbanColumn from "@/components/KanbanColumn";
import AddTaskModal from "@/components/AddTaskModal";
import EnergyWidget from "@/components/EnergyWidget";
import StatsBar from "@/components/StatsBar";
import type { Activity } from "@shared/schema";

const COLUMNS = [
  { status: "in_progress", title: "In Progress", accent: "#22d3ee", icon: "⚡" },
  { status: "planned", title: "Planned", accent: "#818cf8", icon: "📋" },
  { status: "completed", title: "Completed", accent: "#4ade80", icon: "✅" },
  { status: "carry_over", title: "Carry Over", accent: "#fb923c", icon: "🔄" },
  { status: "parking_lot", title: "Parking Lot", accent: "#94a3b8", icon: "🅿️" },
];

export default function Board() {
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [addModalStatus, setAddModalStatus] = useState("planned");
  const [editActivity, setEditActivity] = useState<Activity | null>(null);

  const { data: activities = [], isLoading, refetch } = useQuery<Activity[]>({
    queryKey: ["/api/activities"],
  });

  const nonArchived = activities.filter(a => !a.archivedAt);

  const handleAddTask = (status: string) => {
    setAddModalStatus(status);
    setEditActivity(null);
    setAddModalOpen(true);
  };

  const handleEditTask = (activity: Activity) => {
    setEditActivity(activity);
    setAddModalOpen(true);
  };

  const getByStatus = (status: string) =>
    nonArchived.filter(a => a.status === status).sort((a, b) => {
      // Sort by priority then by date
      const pOrder = { critical: 0, high: 1, medium: 2, low: 3 };
      const pDiff = (pOrder[a.priority as keyof typeof pOrder] || 2) - (pOrder[b.priority as keyof typeof pOrder] || 2);
      if (pDiff !== 0) return pDiff;
      return new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime();
    });

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-border flex-shrink-0">
        <div>
          <h1 className="text-lg font-semibold text-foreground">Activity Board</h1>
          <p className="text-xs text-muted-foreground mono">One Man Army · $10K by June 25</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            data-testid="button-refresh"
            className="h-8 w-8 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            onClick={() => refetch()}
            title="Refresh"
          >
            <RefreshCw size={14} />
          </button>
          <Button
            data-testid="button-add-task-header"
            size="sm"
            className="h-8 bg-primary/20 text-primary border border-primary/30 hover:bg-primary hover:text-primary-foreground text-xs"
            variant="outline"
            onClick={() => handleAddTask("planned")}
          >
            <Plus size={14} className="mr-1" /> New Task
          </Button>
        </div>
      </header>

      {/* Stats bar */}
      <StatsBar />

      {/* Energy widget */}
      <EnergyWidget compact />

      {/* Kanban board */}
      <div className="flex-1 overflow-auto px-4 pb-4">
        {isLoading ? (
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
            Loading board...
          </div>
        ) : (
          <div className="flex gap-3 pt-4" style={{ minWidth: "max-content" }}>
            {COLUMNS.map(col => (
              <div key={col.status} style={{ width: "260px", flexShrink: 0 }}>
                <KanbanColumn
                  {...col}
                  activities={getByStatus(col.status)}
                  onAddTask={handleAddTask}
                  onEditTask={handleEditTask}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Modals */}
      <AddTaskModal
        open={addModalOpen}
        onClose={() => { setAddModalOpen(false); setEditActivity(null); }}
        editActivity={editActivity}
        defaultStatus={addModalStatus}
      />
    </div>
  );
}
