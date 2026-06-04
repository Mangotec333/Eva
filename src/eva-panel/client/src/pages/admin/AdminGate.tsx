import { useState } from "react";
import { Shield } from "lucide-react";
import { apiRequest, setAdminPin } from "@/lib/queryClient";

export default function AdminGate({ onUnlock }: { onUnlock: () => void }) {
  const [pin, setPin] = useState("");
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (pin.length < 4) return;
    setLoading(true);
    try {
      const data = await apiRequest("POST", "/api/admin/auth", { pin }).then(r => r.json());
      if (data.ok) { setAdminPin(pin); onUnlock(); } else { setError(true); setPin(""); }
    } catch { setError(true); setPin(""); }
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-background dark flex items-center justify-center">
      <div className="w-72">
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 rounded-2xl bg-amber-500/10 flex items-center justify-center mb-4">
            <Shield size={22} className="text-amber-400" />
          </div>
          <div className="text-base font-semibold text-foreground">Admin Access</div>
          <div className="text-xs text-muted-foreground mt-1">Enter PIN to continue</div>
        </div>

        <input
          data-testid="input-admin-pin"
          type="password"
          inputMode="numeric"
          maxLength={8}
          placeholder="••••••"
          value={pin}
          onChange={e => { setPin(e.target.value); setError(false); }}
          onKeyDown={e => e.key === "Enter" && submit()}
          className={`w-full bg-card border rounded-xl px-4 py-3 text-center text-lg tracking-[0.5em] text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-primary transition-colors ${
            error ? "border-red-500/50" : "border-border"
          }`}
          autoFocus
        />

        {error && (
          <div className="text-xs text-red-400 text-center mt-2">Incorrect PIN</div>
        )}

        <button
          data-testid="btn-admin-submit"
          onClick={submit}
          disabled={pin.length < 4 || loading}
          className="mt-4 w-full bg-amber-500/15 text-amber-400 border border-amber-500/20 hover:bg-amber-500/25 px-4 py-2.5 rounded-xl text-sm font-medium transition-colors disabled:opacity-40"
        >
          {loading ? "Verifying..." : "Unlock"}
        </button>

        <a href="/#/" className="block text-center text-xs text-muted-foreground/40 hover:text-muted-foreground mt-4 transition-colors">
          ← Back to EVA
        </a>
      </div>
    </div>
  );
}
