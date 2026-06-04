import { Switch, Route, Router } from "wouter";
import { useHashLocation } from "wouter/use-hash-location";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "@/lib/queryClient";
import { Toaster } from "@/components/ui/toaster";
import Board from "@/pages/Board";
import EnergyPage from "@/pages/EnergyPage";
import ActivityLog from "@/pages/ActivityLog";
import Sidebar from "@/components/Sidebar";
import { useState } from "react";

function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <QueryClientProvider client={queryClient}>
      <div className="flex min-h-screen bg-background text-foreground dark">
        <Sidebar collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed(c => !c)} />
        <main className={`flex-1 overflow-auto transition-all duration-200 ${sidebarCollapsed ? "ml-14" : "ml-56"}`}>
          <Router hook={useHashLocation}>
            <Switch>
              <Route path="/" component={Board} />
              <Route path="/energy" component={EnergyPage} />
              <Route path="/log" component={ActivityLog} />
              <Route>
                <div className="flex items-center justify-center h-full text-muted-foreground">Page not found</div>
              </Route>
            </Switch>
          </Router>
        </main>
      </div>
      <Toaster />
    </QueryClientProvider>
  );
}

export default App;
