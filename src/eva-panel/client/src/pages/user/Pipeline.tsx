import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, ExternalLink } from "lucide-react";
import { apiRequest } from "@/lib/queryClient";
import type { Deal } from "@shared/schema";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  scouting: { label: "Scouting", color: "text-slate-400", bg: "bg-slate-400/10" },
  loi: { label: "LOI", color: "text-indigo-400", bg: "bg-indigo-400/10" },
  dd: { label: "Due Diligence", color: "text-cyan-400", bg: "bg-cyan-400/10" },
  negotiation: { label: "Negotiation", color: "text-orange-400", bg: "bg-orange-400/10" },
  closed: { label: "Closed", color: "text-green-400", bg: "bg-green-400/10" },
  dead: { label: "Dead", color: "text-red-400/70", bg: "bg-red-400/10" },
};

const TYPE_ICON: Record<string, string> = {
  acquisition: "🏢", rcfe: "🏥", saas: "⚡", agency: "📣"
};

function AddDealModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [type, setType] = useState("acquisition");
  const [status, setStatus] = useState("scouting");
  const [askPrice, setAskPrice] = useState("");
  const [mrr, setMrr] = useState("");
  const [broker, setBroker] = useState("");
  const [nextAction, setNextAction] = useState("");

  const mutation = useMutation({
    mutationFn: () => apiRequest("POST", "/api/deals", {
      name, type, status,
      askPrice: askPrice || undefined,
      mrr: mrr || undefined,
      broker: broker || undefined,
      nextAction: nextAction || undefined,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["/api/deals"] }); qc.invalidateQueries({ queryKey: ["/api/stats"] }); setName(""); onClose(); },
  });

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="bg-card border-border max-w-sm">
        <DialogHeader><DialogTitle className="text-sm font-semibold">Add Deal</DialogTitle></DialogHeader>
        <div className="space-y-3 mt-1">
          <Input placeholder="Deal name" value={name} onChange={e => setName(e.target.value)} className="bg-muted border-border text-sm" autoFocus />
          <div className="grid grid-cols-2 gap-2">
            <Select value={type} onValueChange={setType}>
              <SelectTrigger className="bg-muted border-border text-xs h-8"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-card border-border">
                <SelectItem value="acquisition">Acquisition</SelectItem>
                <SelectItem value="rcfe">RCFE</SelectItem>
                <SelectItem value="saas">SaaS</SelectItem>
                <SelectItem value="agency">Agency</SelectItem>
              </SelectContent>
            </Select>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger className="bg-muted border-border text-xs h-8"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-card border-border">
                {Object.entries(STATUS_CONFIG).map(([k, v]) => (
                  <SelectItem key={k} value={k}>{v.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Input placeholder="Ask price" value={askPrice} onChange={e => setAskPrice(e.target.value)} className="bg-muted border-border text-xs h-8" />
            <Input placeholder="MRR" value={mrr} onChange={e => setMrr(e.target.value)} className="bg-muted border-border text-xs h-8" />
          </div>
          <Input placeholder="Broker" value={broker} onChange={e => setBroker(e.target.value)} className="bg-muted border-border text-sm" />
          <Input placeholder="Next action" value={nextAction} onChange={e => setNextAction(e.target.value)} className="bg-muted border-border text-sm" />
          <Button onClick={() => mutation.mutate()} disabled={!name.trim() || mutation.isPending}
            className="w-full bg-primary text-primary-foreground text-sm h-9">
            {mutation.isPending ? "Adding..." : "Add Deal"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function Pipeline() {
  const qc = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const { data: deals = [], isLoading } = useQuery<Deal[]>({ queryKey: ["/api/deals"] });

  const activeDeal = deals.filter(d => ["loi", "dd", "negotiation"].includes(d.status));
  const otherDeals = deals.filter(d => !["loi", "dd", "negotiation"].includes(d.status));

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => apiRequest("PATCH", `/api/deals/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["/api/deals"] }),
  });

  return (
    <div className="px-8 py-8 max-w-2xl">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-base font-semibold">Pipeline</h1>
        <button onClick={() => setAddOpen(true)}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-primary border border-border hover:border-primary/40 px-3 py-1.5 rounded-lg transition-colors">
          <Plus size={13} /> New Deal
        </button>
      </div>

      {isLoading ? <div className="text-muted-foreground text-sm">Loading...</div> : (
        <>
          {/* Active deals */}
          {activeDeal.length > 0 && (
            <div className="mb-6">
              <div className="text-xs text-muted-foreground font-medium mb-3 uppercase tracking-wide">Active</div>
              <div className="space-y-2">
                {activeDeal.map(deal => (
                  <DealCard key={deal.id} deal={deal} onUpdate={(data) => updateMutation.mutate({ id: deal.id, data })} />
                ))}
              </div>
            </div>
          )}

          {/* Other deals */}
          {otherDeals.length > 0 && (
            <div>
              <div className="text-xs text-muted-foreground font-medium mb-3 uppercase tracking-wide">Tracking</div>
              <div className="space-y-2">
                {otherDeals.map(deal => (
                  <DealCard key={deal.id} deal={deal} onUpdate={(data) => updateMutation.mutate({ id: deal.id, data })} />
                ))}
              </div>
            </div>
          )}

          {deals.length === 0 && (
            <div className="text-sm text-muted-foreground text-center py-16">No deals yet. Add your first one.</div>
          )}
        </>
      )}

      <AddDealModal open={addOpen} onClose={() => setAddOpen(false)} />
    </div>
  );
}

function DealCard({ deal, onUpdate }: { deal: Deal; onUpdate: (data: any) => void }) {
  const cfg = STATUS_CONFIG[deal.status] || STATUS_CONFIG.scouting;

  return (
    <div data-testid={`deal-${deal.id}`} className="eva-card bg-card border border-border rounded-xl px-4 py-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <span className="text-base flex-shrink-0">{TYPE_ICON[deal.type] || "🏢"}</span>
          <div className="min-w-0">
            <div className="text-sm font-medium text-foreground">{deal.name}</div>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${cfg.bg} ${cfg.color}`}>
                {cfg.label}
              </span>
              {deal.mrr && <span className="text-[10px] text-muted-foreground mono">MRR {deal.mrr}</span>}
              {deal.askPrice && <span className="text-[10px] text-muted-foreground mono">Ask {deal.askPrice}</span>}
              {deal.broker && <span className="text-[10px] text-muted-foreground">via {deal.broker}</span>}
            </div>
          </div>
        </div>
        {deal.ddFolderUrl && (
          <a href={deal.ddFolderUrl} target="_blank" rel="noopener noreferrer"
            className="text-muted-foreground hover:text-primary transition-colors flex-shrink-0">
            <ExternalLink size={13} />
          </a>
        )}
      </div>
      {deal.nextAction && (
        <div className="mt-2.5 text-xs text-muted-foreground border-t border-border pt-2">
          → {deal.nextAction}
        </div>
      )}
    </div>
  );
}
