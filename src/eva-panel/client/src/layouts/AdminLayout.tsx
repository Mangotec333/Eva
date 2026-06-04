import { Link, useLocation } from "wouter";
import { Shield, Activity, Clock, DollarSign, LogOut } from "lucide-react";

const NAV = [
  { href: "/admin", icon: Activity, label: "Operations" },
  { href: "/admin/crons", icon: Clock, label: "Crons" },
  { href: "/admin/costs", icon: DollarSign, label: "Cost Gate" },
];

export default function AdminLayout({ children, onLock }: { children: React.ReactNode; onLock: () => void }) {
  const [location] = useLocation();

  return (
    <div className="flex min-h-screen admin-surface dark">
      {/* Sidebar */}
      <aside className="w-52 flex-shrink-0 flex flex-col border-r border-border">
        <div className="flex items-center gap-3 px-5 py-5 border-b border-border">
          <div className="w-7 h-7 rounded-lg bg-amber-500/15 flex items-center justify-center flex-shrink-0">
            <Shield size={14} className="text-amber-400" />
          </div>
          <div>
            <div className="text-sm font-semibold text-amber-400 tracking-wide">Admin</div>
            <div className="text-[10px] text-muted-foreground mono">EVA ops layer</div>
          </div>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-0.5">
          {NAV.map(({ href, icon: Icon, label }) => {
            const active = location === href;
            return (
              <Link key={href} href={href}>
                <a data-testid={`admin-nav-${label.toLowerCase()}`}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                    active ? "bg-amber-500/10 text-amber-400 font-medium" : "text-muted-foreground hover:text-foreground hover:bg-accent"
                  }`}>
                  <Icon size={16} className="flex-shrink-0" />
                  {label}
                </a>
              </Link>
            );
          })}
        </nav>

        <div className="px-3 pb-5 pt-3 border-t border-border space-y-2">
          <Link href="/">
            <a className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-muted-foreground hover:text-foreground hover:bg-accent transition-colors w-full">
              ← User Panel
            </a>
          </Link>
          <button
            onClick={onLock}
            data-testid="button-admin-lock"
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-muted-foreground hover:text-red-400 hover:bg-red-500/5 transition-colors w-full"
          >
            <LogOut size={12} /> Lock Admin
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-auto">
        <div className="page-enter">{children}</div>
      </main>
    </div>
  );
}
