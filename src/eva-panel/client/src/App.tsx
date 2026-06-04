import { Switch, Route, Router } from "wouter";
import { useHashLocation } from "wouter/use-hash-location";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "@/lib/queryClient";
import { Toaster } from "@/components/ui/toaster";
import { useState } from "react";

// User panel
import UserLayout from "@/layouts/UserLayout";
import Dashboard from "@/pages/user/Dashboard";
import Board from "@/pages/user/Board";
import Pipeline from "@/pages/user/Pipeline";
import Intelligence from "@/pages/user/Intelligence";

// Admin panel
import AdminGate from "@/pages/admin/AdminGate";
import AdminLayout from "@/layouts/AdminLayout";
import AdminOps from "@/pages/admin/AdminOps";
import AdminCrons from "@/pages/admin/AdminCrons";
import AdminCosts from "@/pages/admin/AdminCosts";

export const AdminContext = { pin: "" };

function App() {
  const [adminUnlocked, setAdminUnlocked] = useState(false);

  return (
    <QueryClientProvider client={queryClient}>
      <Router hook={useHashLocation}>
        <Switch>
          {/* Admin routes */}
          <Route path="/admin">
            {adminUnlocked
              ? <AdminLayout onLock={() => setAdminUnlocked(false)}><AdminOps /></AdminLayout>
              : <AdminGate onUnlock={() => setAdminUnlocked(true)} />}
          </Route>
          <Route path="/admin/crons">
            {adminUnlocked
              ? <AdminLayout onLock={() => setAdminUnlocked(false)}><AdminCrons /></AdminLayout>
              : <AdminGate onUnlock={() => setAdminUnlocked(true)} />}
          </Route>
          <Route path="/admin/costs">
            {adminUnlocked
              ? <AdminLayout onLock={() => setAdminUnlocked(false)}><AdminCosts /></AdminLayout>
              : <AdminGate onUnlock={() => setAdminUnlocked(true)} />}
          </Route>

          {/* User routes */}
          <Route path="/board">
            <UserLayout><Board /></UserLayout>
          </Route>
          <Route path="/pipeline">
            <UserLayout><Pipeline /></UserLayout>
          </Route>
          <Route path="/intelligence">
            <UserLayout><Intelligence /></UserLayout>
          </Route>
          <Route>
            <UserLayout><Dashboard /></UserLayout>
          </Route>
        </Switch>
      </Router>
      <Toaster />
    </QueryClientProvider>
  );
}

export default App;
