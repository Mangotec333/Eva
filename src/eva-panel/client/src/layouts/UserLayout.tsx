import { Link, useLocation } from "wouter";
import { useQuery } from "@tanstack/react-query";
import { LayoutDashboard, Kanban, TrendingUp, Inbox, Settings } from "lucide-react";

const NAV = [
  { href: "/", icon: LayoutDashboard, label: "Dashboard" },
  { href: "/board", icon: Kanban, label: "Board" },
  { href: "/pipeline", icon: TrendingUp, label: "Pipeline" },
  { href: "/intelligence", icon: Inbox, label: "Intelligence" },
];

export default function UserLayout({ children }: { children: React.ReactNode }) {
  const [location] = useLocation();
  const { data: stats } = useQuery<any>({ queryKey: ["/api/stats"], refetchInterval: 30000 });
  const unread = stats?.unread_notifications ?? 0;

  return (
    <div className="flex min-h-screen bg-background dark">
      {/* Sidebar */}
      <aside className="w-52 flex-shrink-0 flex flex-col border-r border-border">
        {/* Logo */}
        <div className="flex items-center gap-3 px-5 py-5 border-b border-border">
          <svg viewBox="0 0 28 28" fill="none" className="w-7 h-7 flex-shrink-0" aria-label="EVA">
            <rect width="28" height="28" rx="7" fill="hsl(186 80% 42% / 0.12)" />
            <path d="M7 9h10M7 14h7M7 19h10" stroke="hsl(186,80%,42%)" strokeWidth="2" strokeLinecap="round"/>
            <circle cx="21" cy="14" r="2.5" fill="hsl(186,80%,42%)" className="dot-pulse"/>
          </svg>
          <div>
            <div className="text-sm font-semibold tracking-wide text-foreground">EVA</div>
            <div className="text-[10px] text-muted-foreground mono">mangotec.ai</div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-0.5">
          {NAV.map(({ href, icon: Icon, label }) => {
            const active = href === "/" ? (location === "/" || location === "") : location.startsWith(href);
            return (
              <Link key={href} href={href}>
                <a data-testid={`nav-${label.toLowerCase()}`}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors relative ${
                    active ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:text-foreground hover:bg-accent"
                  }`}>
                  <Icon size={16} className="flex-shrink-0" />
                  <span>{label}</span>
                  {label === "Intelligence" && unread > 0 && (
                    <span className="ml-auto text-[10px] mono bg-primary/20 text-primary px-1.5 py-0.5 rounded-full">{unread}</span>
                  )}
                </a>
              </Link>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="px-5 pb-5 pt-3 border-t border-border space-y-2">
          <div className="text-[11px] text-muted-foreground mono">$10K · June 25</div>
          {stats && (
            <div className="text-[11px] text-muted-foreground">
              {stats.tasks_in_progress} active · {stats.deals_active} deals
            </div>
          )}
          <Link href="/admin">
            <a className="flex items-center gap-1.5 text-[11px] text-muted-foreground/50 hover:text-muted-foreground transition-colors mt-1">
              <Settings size={11} /> Admin
            </a>
          </Link>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto">
        <div className="page-enter">
          {children}
        </div>
      </main>
    </div>
  );
}
