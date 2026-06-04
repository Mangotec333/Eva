import { Link, useLocation } from "wouter";
import { LayoutDashboard, Zap, ScrollText, ChevronLeft, ChevronRight } from "lucide-react";

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

const navItems = [
  { href: "/", icon: LayoutDashboard, label: "Activity Board" },
  { href: "/energy", icon: Zap, label: "Energy Log" },
  { href: "/log", icon: ScrollText, label: "Audit Log" },
];

export default function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const [location] = useLocation();

  return (
    <aside
      className={`fixed left-0 top-0 h-screen z-40 flex flex-col border-r border-border bg-card transition-all duration-200 ${collapsed ? "w-14" : "w-56"}`}
    >
      {/* Logo */}
      <div className={`flex items-center gap-3 p-4 border-b border-border ${collapsed ? "justify-center" : ""}`}>
        <div className="w-8 h-8 flex-shrink-0">
          <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-label="EVA Logo">
            <rect width="32" height="32" rx="8" fill="hsl(187 85% 43% / 0.15)" />
            <path d="M8 10h12M8 16h8M8 22h12" stroke="hsl(187, 85%, 43%)" strokeWidth="2.5" strokeLinecap="round" />
            <circle cx="24" cy="16" r="3" fill="hsl(187, 85%, 43%)" className="status-pulse" />
          </svg>
        </div>
        {!collapsed && (
          <div>
            <div className="text-sm font-semibold text-foreground tracking-wide">EVA</div>
            <div className="text-xs text-muted-foreground mono">Command Center</div>
          </div>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 p-2 space-y-1">
        {navItems.map(({ href, icon: Icon, label }) => {
          const isActive = location === href;
          return (
            <Link key={href} href={href}>
              <a
                data-testid={`nav-${label.toLowerCase().replace(/\s/g, "-")}`}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-primary/15 text-primary"
                    : "text-muted-foreground hover:text-foreground hover:bg-accent"
                } ${collapsed ? "justify-center" : ""}`}
                title={collapsed ? label : undefined}
              >
                <Icon size={18} className="flex-shrink-0" />
                {!collapsed && <span>{label}</span>}
                {isActive && !collapsed && (
                  <div className="ml-auto w-1.5 h-1.5 rounded-full bg-primary" />
                )}
              </a>
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      {!collapsed && (
        <div className="p-4 border-t border-border">
          <div className="text-xs text-muted-foreground mono">$10K / June 25</div>
          <div className="text-xs text-muted-foreground mt-0.5">One Man Army 🔥</div>
        </div>
      )}

      {/* Collapse toggle */}
      <button
        onClick={onToggle}
        data-testid="button-sidebar-toggle"
        className="absolute -right-3 top-1/2 -translate-y-1/2 w-6 h-6 rounded-full bg-card border border-border flex items-center justify-center text-muted-foreground hover:text-foreground hover:border-primary/50 transition-colors z-50"
      >
        {collapsed ? <ChevronRight size={12} /> : <ChevronLeft size={12} />}
      </button>
    </aside>
  );
}
