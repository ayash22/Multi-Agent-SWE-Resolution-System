import { ReactNode } from "react";
import { HealthState } from "../../lib/health";
import { RunRecord } from "../../lib/types";
import Sidebar, { ViewId } from "./Sidebar";

export default function AppShell({
  view,
  onNavigate,
  runs,
  activeRunId,
  onSelectRun,
  onRemoveRun,
  health,
  children,
}: {
  view: ViewId;
  onNavigate: (view: ViewId) => void;
  runs: RunRecord[];
  activeRunId: string | null;
  onSelectRun: (id: string) => void;
  onRemoveRun: (id: string) => void;
  health: HealthState;
  children: ReactNode;
}) {
  return (
    <div className="flex h-screen w-full overflow-hidden bg-app text-primary">
      <Sidebar
        view={view}
        onNavigate={onNavigate}
        runs={runs}
        activeRunId={activeRunId}
        onSelectRun={onSelectRun}
        onRemoveRun={onRemoveRun}
        health={health}
      />
      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">{children}</main>
    </div>
  );
}
