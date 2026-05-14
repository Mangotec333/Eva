import { Switch, Route, Router } from "wouter";
import { useHashLocation } from "wouter/use-hash-location";
import { queryClient } from "./lib/queryClient";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import NotFound from "@/pages/not-found";
import Home from "@/pages/Home";
import Checkin from "@/pages/Checkin";
import GoalsPage from "@/pages/Goals";
import HistoryPage from "@/pages/History";
import ActivityPage from "@/pages/Activity";
import { useEffect } from "react";

function AppRouter() {
  return (
    <Switch>
      <Route path="/" component={Home} />
      <Route path="/checkin" component={Checkin} />
      <Route path="/goals" component={GoalsPage} />
      <Route path="/history" component={HistoryPage} />
      <Route path="/activity" component={ActivityPage} />
      <Route component={NotFound} />
    </Switch>
  );
}

function App() {
  // App is dark-mode only — force the .dark class on root.
  useEffect(() => {
    document.documentElement.classList.add("dark");
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <Toaster />
        <Router hook={useHashLocation}>
          <AppRouter />
        </Router>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
