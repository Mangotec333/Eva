import { useQuery } from "@tanstack/react-query";
import { ScrollText, Clock } from "lucide-react";
import type { ActivityEvent } from "@shared/schema";

const EVENT_ICONS: Record<string, string> = {
  created: "✨",
  status_changed: "🔀",
  done_clicked: "✅",
  edited: "✏️",
  archived: "🗂️",
};

const EVENT_COLORS: Record<string, string> = {
  created: "text-cyan-400",
  status_changed: "text-blue-400",
  done_clicked: "text-green-400",
  edited: "text-yellow-400",
  archived: "text-slate-400",
};

export default function ActivityLog() {
  const { data: events = [], isLoading } = useQuery<ActivityEvent[]>({
    queryKey: ["/api/events"],
  });

  const formatTime = (ts: string) => {
    const d = new Date(ts);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  };

  return (
    <div className="p-6 max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-lg font-semibold flex items-center gap-2">
            <ScrollText size={20} className="text-muted-foreground" />
            Audit Log
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5 mono">
            Every action timestamped · {events.length} events · never deleted
          </p>
        </div>
      </div>

      {/* Timeline */}
      {isLoading ? (
        <div className="text-muted-foreground text-sm">Loading...</div>
      ) : events.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground/40">
          <ScrollText size={40} className="mx-auto mb-4 opacity-30" />
          <p className="text-sm">No activity yet. Start adding tasks to see the audit trail.</p>
        </div>
      ) : (
        <div className="relative">
          {/* Timeline line */}
          <div className="absolute left-5 top-0 bottom-0 w-px bg-border" />

          <div className="space-y-1">
            {events.map((event, idx) => (
              <div
                key={event.id}
                data-testid={`event-${event.id}`}
                className="flex items-start gap-4 pl-12 py-2.5 relative"
              >
                {/* Dot */}
                <div
                  className="absolute left-3.5 top-3.5 w-3 h-3 rounded-full border-2 border-background"
                  style={{
                    background: event.eventType === "done_clicked" ? "#4ade80" :
                                event.eventType === "created" ? "#22d3ee" :
                                event.eventType === "archived" ? "#64748b" :
                                "#818cf8",
                  }}
                />

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="text-base">{EVENT_ICONS[event.eventType] || "•"}</span>
                      <div>
                        <span className={`text-xs font-semibold ${EVENT_COLORS[event.eventType] || "text-muted-foreground"}`}>
                          {event.eventType.replace(/_/g, " ")}
                        </span>
                        {event.fromStatus && event.toStatus && (
                          <span className="text-xs text-muted-foreground ml-1.5">
                            {event.fromStatus} → {event.toStatus}
                          </span>
                        )}
                        {event.note && (
                          <p className="text-xs text-muted-foreground mt-0.5 italic">{event.note}</p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 text-xs text-muted-foreground mono flex-shrink-0">
                      <Clock size={10} />
                      {formatTime(event.timestamp)}
                    </div>
                  </div>
                  <div className="text-xs text-muted-foreground/60 mono mt-0.5 ml-6">
                    task #{event.activityId}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
