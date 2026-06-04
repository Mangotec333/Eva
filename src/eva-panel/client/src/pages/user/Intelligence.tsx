import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCheck, Inbox } from "lucide-react";
import { apiRequest } from "@/lib/queryClient";
import type { Notification } from "@shared/schema";

const TYPE_CONFIG: Record<string, { icon: string; color: string }> = {
  brief: { icon: "☀️", color: "text-yellow-400" },
  deal_signal: { icon: "📊", color: "text-cyan-400" },
  alert: { icon: "⚠️", color: "text-orange-400" },
  system: { icon: "⚙️", color: "text-slate-400" },
};

export default function Intelligence() {
  const qc = useQueryClient();
  const { data: notifications = [], isLoading } = useQuery<Notification[]>({ queryKey: ["/api/notifications"] });

  const readMutation = useMutation({
    mutationFn: (id: number) => apiRequest("POST", `/api/notifications/${id}/read`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["/api/notifications"] }); qc.invalidateQueries({ queryKey: ["/api/stats"] }); },
  });

  const readAllMutation = useMutation({
    mutationFn: () => apiRequest("POST", "/api/notifications/read-all"),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["/api/notifications"] }); qc.invalidateQueries({ queryKey: ["/api/stats"] }); },
  });

  const unread = notifications.filter(n => !n.read);
  const read = notifications.filter(n => n.read);

  const formatTime = (ts: string) => {
    const d = new Date(ts);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    if (diff < 3600000) return `${Math.round(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.round(diff / 3600000)}h ago`;
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };

  return (
    <div className="px-8 py-8 max-w-2xl">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-base font-semibold">Intelligence</h1>
          {unread.length > 0 && (
            <p className="text-xs text-muted-foreground mt-0.5">{unread.length} unread</p>
          )}
        </div>
        {unread.length > 0 && (
          <button onClick={() => readAllMutation.mutate()}
            data-testid="btn-read-all"
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground border border-border px-3 py-1.5 rounded-lg transition-colors">
            <CheckCheck size={12} /> Mark all read
          </button>
        )}
      </div>

      {isLoading ? (
        <div className="text-muted-foreground text-sm">Loading...</div>
      ) : notifications.length === 0 ? (
        <div className="text-center py-16">
          <Inbox size={32} className="mx-auto mb-3 text-muted-foreground/30" />
          <p className="text-sm text-muted-foreground">No messages yet.</p>
          <p className="text-xs text-muted-foreground mt-1">EVA morning/midday/evening briefs will appear here.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {/* Unread */}
          {unread.map(n => (
            <NotifCard key={n.id} n={n} onRead={() => readMutation.mutate(n.id)} formatTime={formatTime} />
          ))}

          {/* Read */}
          {read.length > 0 && unread.length > 0 && (
            <div className="py-3">
              <div className="text-[10px] text-muted-foreground uppercase tracking-wide font-medium">Earlier</div>
            </div>
          )}
          {read.slice(0, 10).map(n => (
            <NotifCard key={n.id} n={n} onRead={() => {}} formatTime={formatTime} dimmed />
          ))}
        </div>
      )}
    </div>
  );
}

function NotifCard({ n, onRead, formatTime, dimmed = false }: {
  n: Notification; onRead: () => void; formatTime: (ts: string) => string; dimmed?: boolean;
}) {
  const cfg = TYPE_CONFIG[n.type] || TYPE_CONFIG.brief;
  return (
    <div data-testid={`notif-${n.id}`}
      onClick={!n.read ? onRead : undefined}
      className={`eva-card rounded-xl border px-4 py-3.5 transition-all ${
        !n.read ? "bg-card border-border cursor-pointer hover:border-primary/30" : "bg-muted/30 border-border/50"
      } ${dimmed ? "opacity-60" : ""}`}>
      <div className="flex items-start gap-3">
        <span className="text-base flex-shrink-0 mt-0.5">{cfg.icon}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div className={`text-sm font-medium ${!n.read ? "text-foreground" : "text-muted-foreground"}`}>
              {n.title}
            </div>
            <div className="text-[10px] text-muted-foreground mono flex-shrink-0">{formatTime(n.createdAt)}</div>
          </div>
          <div className="text-xs text-muted-foreground mt-1 leading-relaxed whitespace-pre-line">{n.body}</div>
        </div>
        {!n.read && (
          <div className="w-1.5 h-1.5 rounded-full bg-primary flex-shrink-0 mt-1.5 dot-pulse" />
        )}
      </div>
    </div>
  );
}
