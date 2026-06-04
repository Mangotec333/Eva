import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, CheckCircle2, ChevronDown } from "lucide-react";
import { apiRequest } from "@/lib/queryClient";
import type { Activity } from "@shared/schema";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const COLS = [
  { status: "in_progress", label: "In Progress", accent: "#22d3ee", dot: "bg-cyan-400" },
  { status: "planned", label: "Planned", accent: "#818cf8", dot: "bg-indigo-400" },
  { status: "completed", label: "Completed", accent: "#4ade80", dot: "bg-green-400" },
  { status: "carry_over", label: "Carry Over", accent: "#fb923c", dot: "bg-orange-400" },
  { status: "parking_lot", label: "Parking Lot", accent: "#94a3b8", dot: "bg-slate-400" },
];

const PRIORITY_DOT: Record<string, string> = {
  critical: "bg-red-400", high: "bg-orange-400", medium: "bg-yellow-400", low: "bg-slate-600"
};

function AddTaskModal({ open, onClose, defaultStatus }: { open: boolean; onClose: () => void; defaultStatus: string }) {
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [status, setStatus] = useState(defaultStatus);
  const [priority, setPriority] = useState("medium");
  const [category, setCategory] = useState("general");

  const mutation = useMutation({
    mutationFn: () => apiRequest("POST", "/api/activities", {
      title, description: desc || undefined, status, priority, category, tags: "[]"
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["/api/activities"] });
      qc.invalidateQueries({ queryKey: ["/api/stats"] });
      setTitle(""); setDesc(""); onClose();
    },
  });

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="bg-card border-border max-w-sm">
        <DialogHeader>
          <DialogTitle className="text-sm font-semibold">New Task</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 mt-1">
          <Input data-testid="input-title" placeholder="What needs to get done?" value={title}
            onChange={e => setTitle(e.target.value)} className="bg-muted border-border text-sm" autoFocus />
          <Textarea placeholder="Notes..." value={desc} onChange={e => setDesc(e.target.value)}
            className="bg-muted border-border text-sm resize-none" rows={2} />
          <div className="grid grid-cols-2 gap-2">
            <Select value={priority} onValueChange={setPriority}>
              <SelectTrigger className="bg-muted border-border text-xs h-8"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-card border-border">
                <SelectItem value="critical">Critical</SelectItem>
                <SelectItem value="high">High</SelectItem>
                <SelectItem value="medium">Medium</SelectItem>
                <SelectItem value="low">Low</SelectItem>
              </SelectContent>
            </Select>
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger className="bg-muted border-border text-xs h-8"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-card border-border">
                <SelectItem value="acquisition">Acquisition</SelectItem>
                <SelectItem value="revenue">Revenue</SelectItem>
                <SelectItem value="eva_build">EVA Build</SelectItem>
                <SelectItem value="operations">Operations</SelectItem>
                <SelectItem value="outreach">Outreach</SelectItem>
                <SelectItem value="general">General</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Button onClick={() => mutation.mutate()} disabled={!title.trim() || mutation.isPending}
            className="w-full bg-primary text-primary-foreground hover:bg-primary/90 text-sm h-9">
            {mutation.isPending ? "Adding..." : "Add Task"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function TaskCard({ task, onDone, onMove }: { task: Activity; onDone: () => void; onMove: (status: string) => void }) {
  const [showMove, setShowMove] = useState(false);
  const isDone = task.status === "completed";

  return (
    <div data-testid={`card-${task.id}`} className="eva-card bg-card border border-border rounded-xl p-3 group">
      <div className="flex items-start gap-2">
        <div className={`w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${PRIORITY_DOT[task.priority] || "bg-slate-600"}`} />
        <div className="flex-1 min-w-0">
          <div className={`text-sm leading-snug ${isDone ? "line-through text-muted-foreground" : "text-foreground"}`}>
            {task.title}
          </div>
          {task.description && (
            <div className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{task.description}</div>
          )}
          <div className="text-[10px] text-muted-foreground mono mt-1.5">
            {task.category.replace("_", " ")}
          </div>
        </div>
      </div>
      {!isDone && (
        <div className="flex items-center gap-1.5 mt-2.5">
          <button data-testid={`done-${task.id}`} onClick={onDone}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-green-400 px-2 py-1 rounded-md hover:bg-green-400/5 transition-colors border border-border hover:border-green-400/30">
            <CheckCircle2 size={11} /> Done
          </button>
          <div className="relative">
            <button onClick={() => setShowMove(s => !s)}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground px-2 py-1 rounded-md hover:bg-accent transition-colors border border-border">
              Move <ChevronDown size={10} />
            </button>
            {showMove && (
              <div className="absolute top-full left-0 mt-1 w-32 bg-card border border-border rounded-lg shadow-lg z-20 py-1">
                {COLS.filter(c => c.status !== task.status).map(c => (
                  <button key={c.status} onClick={() => { onMove(c.status); setShowMove(false); }}
                    className="w-full text-left px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-accent">
                    {c.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function Board() {
  const qc = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [addStatus, setAddStatus] = useState("planned");
  const { data: activities = [], isLoading } = useQuery<Activity[]>({ queryKey: ["/api/activities"] });

  const doneMutation = useMutation({
    mutationFn: (id: number) => apiRequest("POST", `/api/activities/${id}/done`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["/api/activities"] }); qc.invalidateQueries({ queryKey: ["/api/stats"] }); },
  });
  const moveMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      apiRequest("PATCH", `/api/activities/${id}/status`, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["/api/activities"] }),
  });

  const byStatus = (s: string) => activities.filter(a => a.status === s)
    .sort((a, b) => {
      const p = { critical: 0, high: 1, medium: 2, low: 3 };
      return (p[a.priority as keyof typeof p] ?? 2) - (p[b.priority as keyof typeof p] ?? 2);
    });

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-8 py-5 border-b border-border flex-shrink-0">
        <h1 className="text-base font-semibold">Board</h1>
        <button data-testid="btn-add-task" onClick={() => { setAddStatus("planned"); setAddOpen(true); }}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-primary border border-border hover:border-primary/40 px-3 py-1.5 rounded-lg transition-colors">
          <Plus size={13} /> New Task
        </button>
      </div>

      {/* Columns */}
      <div className="flex-1 overflow-x-auto overflow-y-hidden px-8 py-5">
        {isLoading ? (
          <div className="text-muted-foreground text-sm">Loading...</div>
        ) : (
          <div className="flex gap-4 h-full" style={{ minWidth: "max-content" }}>
            {COLS.map(col => {
              const tasks = byStatus(col.status);
              return (
                <div key={col.status} className="flex flex-col w-56 flex-shrink-0">
                  {/* Col header */}
                  <div className="flex items-center justify-between mb-2.5">
                    <div className="flex items-center gap-2">
                      <div className={`w-1.5 h-1.5 rounded-full ${col.dot}`} />
                      <span className="text-xs font-medium text-foreground">{col.label}</span>
                      <span className="text-xs mono text-muted-foreground">{tasks.length}</span>
                    </div>
                    <button onClick={() => { setAddStatus(col.status); setAddOpen(true); }}
                      className="text-muted-foreground hover:text-foreground transition-colors">
                      <Plus size={13} />
                    </button>
                  </div>
                  {/* Accent line */}
                  <div className="h-px rounded-full mb-3" style={{ background: `linear-gradient(to right, ${col.accent}50, transparent)` }} />
                  {/* Cards */}
                  <div className="space-y-2 overflow-y-auto flex-1">
                    {tasks.length === 0 ? (
                      <div className="text-xs text-muted-foreground/30 text-center py-6">Empty</div>
                    ) : tasks.map(t => (
                      <TaskCard key={t.id} task={t}
                        onDone={() => doneMutation.mutate(t.id)}
                        onMove={(status) => moveMutation.mutate({ id: t.id, status })} />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <AddTaskModal open={addOpen} onClose={() => setAddOpen(false)} defaultStatus={addStatus} />
    </div>
  );
}
