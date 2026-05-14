import { Link, useLocation } from 'wouter';
import { Home, Target, History, Activity } from 'lucide-react';
import { cn } from '@/lib/utils';
import { EvaLogo } from './EvaLogo';

const NAV = [
  { href: '/', label: 'Today', icon: Home },
  { href: '/goals', label: 'Goals', icon: Target },
  { href: '/history', label: 'History', icon: History },
  { href: '/activity', label: 'Activity', icon: Activity },
];

export function EvaLayout({ children }: { children: React.ReactNode }) {
  const [loc] = useLocation();
  return (
    <div className="min-h-screen flex flex-col md:flex-row">
      {/* Sidebar */}
      <aside className="md:w-60 md:border-r border-b md:border-b-0 border-border bg-sidebar md:min-h-screen">
        <div className="px-5 md:px-6 py-4 md:py-6 flex flex-col md:items-start gap-3 md:gap-6">
          <Link href="/">
            <a
              className="flex items-center gap-3 hover-elevate rounded-md px-1 py-1 self-start"
              data-testid="link-home-logo"
            >
              <EvaLogo className="h-7 w-7 text-primary" />
              <div className="leading-tight">
                <div className="text-sm font-medium tracking-tight">EVA</div>
                <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                  Morning OS
                </div>
              </div>
            </a>
          </Link>
          <nav className="flex md:flex-col gap-1 md:mt-2 md:w-full overflow-x-auto -mx-1 px-1">
            {NAV.map((item) => {
              const Icon = item.icon;
              const active = loc === item.href;
              return (
                <Link key={item.href} href={item.href}>
                  <a
                    data-testid={`link-nav-${item.label.toLowerCase()}`}
                    className={cn(
                      'flex items-center gap-2 md:gap-3 px-3 py-2 rounded-md text-sm hover-elevate whitespace-nowrap',
                      active
                        ? 'bg-sidebar-accent text-foreground'
                        : 'text-muted-foreground'
                    )}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    <span>{item.label}</span>
                  </a>
                </Link>
              );
            })}
          </nav>
        </div>
      </aside>
      {/* Main */}
      <main className="flex-1 min-w-0">{children}</main>
    </div>
  );
}
