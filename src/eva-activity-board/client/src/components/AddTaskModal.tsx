import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import type { Activity } from "@shared/schema";

interface AddTaskModalProps {
  open: boolean;
  onClose: () => void;
  editActivity?: Activity | null;
  defaultStatus?: string;
}

export default function AddTaskModal({ open, onClose, editActivity, defaultStatus = "planned" }: AddTaskModalProps) {
  const qc = useQueryClient();
  const { toast } = useToast();

  const [title, setTitle] = useState(editActivity?.title || "");
  const [description, setDescription] = useState(editActivity?.description || "");
  const [status, setStatus] = useState(editActivity?.status || defaultStatus);
  const [priority, setPriority] = useState(editActivity?.priority || "medium");
  const [category, setCategory] = useState(editActivity?.category || "general");
  const [tags, setTags] = useState(() => {
    try { return JSON.parse(editActivity?.tags || "[]").join(", "); } catch { return ""; }
  });
  const [dueDate, setDueDate] = useState(editActivity?.dueDate || "");

  const isEdit = !!editActivity;

  const mutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => {
      if (isEdit) {
        return apiRequest("PATCH", `/api/activities/${editActivity.id}`, data);
      }
      return apiRequest("POST", "/api/activities", data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["/api/activities"] });
      qc.invalidateQueries({ queryKey: ["/api/stats"] });
      toast({ title: isEdit ? "Task updated" : "Task created", description: title });
      onClose();
    },
    onError: (e) => {
      toast({ title: "Error", description: String(e), variant: "destructive" });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    const tagArray = tags.split(",").map(t => t.trim()).filter(Boolean);
    mutation.mutate({
      title: title.trim(),
      description: description.trim() || undefined,
      status,
      priority,
      category,
      tags: JSON.stringify(tagArray),
      dueDate: dueDate || undefined,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="bg-card border-border max-w-md">
        <DialogHeader>
          <DialogTitle className="text-foreground">
            {isEdit ? "Edit Task" : "Add Task"}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 mt-2">
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Title *</Label>
            <Input
              data-testid="input-task-title"
              placeholder="What needs to get done?"
              value={title}
              onChange={e => setTitle(e.target.value)}
              className="bg-muted border-border text-sm"
              autoFocus
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Description</Label>
            <Textarea
              data-testid="input-task-description"
              placeholder="Context, links, notes..."
              value={description}
              onChange={e => setDescription(e.target.value)}
              className="bg-muted border-border text-sm resize-none"
              rows={3}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Status</Label>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger data-testid="select-status" className="bg-muted border-border text-sm h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-card border-border">
                  <SelectItem value="planned">Planned</SelectItem>
                  <SelectItem value="in_progress">In Progress</SelectItem>
                  <SelectItem value="completed">Completed</SelectItem>
                  <SelectItem value="carry_over">Carry Over</SelectItem>
                  <SelectItem value="parking_lot">Parking Lot</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Priority</Label>
              <Select value={priority} onValueChange={setPriority}>
                <SelectTrigger data-testid="select-priority" className="bg-muted border-border text-sm h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-card border-border">
                  <SelectItem value="critical">🔴 Critical</SelectItem>
                  <SelectItem value="high">🟠 High</SelectItem>
                  <SelectItem value="medium">🟡 Medium</SelectItem>
                  <SelectItem value="low">⚪ Low</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Category</Label>
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger data-testid="select-category" className="bg-muted border-border text-sm h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-card border-border">
                <SelectItem value="acquisition">🏢 Acquisition</SelectItem>
                <SelectItem value="revenue">💰 Revenue</SelectItem>
                <SelectItem value="eva_build">🤖 EVA Build</SelectItem>
                <SelectItem value="operations">⚙️ Operations</SelectItem>
                <SelectItem value="outreach">📨 Outreach</SelectItem>
                <SelectItem value="general">📋 General</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Tags (comma separated)</Label>
            <Input
              data-testid="input-tags"
              placeholder="batchai, heloc, ghl..."
              value={tags}
              onChange={e => setTags(e.target.value)}
              className="bg-muted border-border text-sm"
            />
          </div>

          <div className="flex gap-2 pt-1">
            <Button
              type="submit"
              data-testid="button-submit-task"
              className="flex-1 bg-primary text-primary-foreground hover:bg-primary/90"
              disabled={mutation.isPending || !title.trim()}
            >
              {mutation.isPending ? "Saving..." : isEdit ? "Save Changes" : "Add Task"}
            </Button>
            <Button type="button" variant="outline" onClick={onClose} className="border-border">
              Cancel
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
