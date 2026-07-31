import { BarChart3, Bot, Circle, Plus, X } from "lucide-react";
import { HealthState } from "../../lib/health";
import { formatRelativeTime, shortSha } from "../../lib/format";
import { runOutcomeVisual } from "../../lib/status";
import { RunRecord } from "../../lib/types";
import StatusPill from "../ui/StatusPill";

export type ViewId = "new" | "run" | "eval";

export default function Sidebar({
  view,
  onNavigate,
  runs,
  activeRunId,
  onSelectRun,
  onRemoveRun,
  health,
}: {
  view: ViewId;
  onNavigate: (view: ViewId) => void;
  runs: RunRecord[];
  activeRunId: string | null;
  onSelectRun: (id: string) => void;
  onRemoveRun: (id: string) => void;
  health: HealthState;
}) {
  return (
    <aside className="flex h-screen w-72 shrink-0 flex-col border-r border-border-subtle bg-surface">
      <div className="flex items-center gap-2.5 border-b border-border-subtle px-5 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent-muted text-accent-hover">
          <Bot size={17} />
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-primary">SWE-Agent</div>
          <div className="truncate text-[11px] text-tertiary">Multi-agent resolution system</div>
        </div>
      </div>

      <div className="px-3 pt-3">
        <button
          onClick={() => onNavigate("new")}
          className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
            view === "new"
              ? "bg-accent-muted text-accent-hover"
              : "text-secondary hover:bg-elevated hover:text-primary"
          }`}
        >
          <Plus size={15} />
          New run
        </button>
        <button
          onClick={() => onNavigate("eval")}
          className={`mt-1 flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
            view === "eval"
              ? "bg-accent-muted text-accent-hover"
              : "text-secondary hover:bg-elevated hover:text-primary"
          }`}
        >
          <BarChart3 size={15} />
          Evaluation
        </button>
      </div>

      <div className="mt-5 flex min-h-0 flex-1 flex-col px-3">
        <div className="px-2 pb-2 text-[11px] font-semibold uppercase tracking-wider text-tertiary">
          Recent runs
        </div>
        <div className="flex-1 space-y-0.5 overflow-y-auto pb-3">
          {runs.length === 0 && (
            <div className="px-2 py-4 text-xs text-tertiary">
              Runs you submit this session will show up here.
            </div>
          )}
          {runs.map((run) => {
            const visual = runOutcomeVisual(run.outcome);
            const isActive = view === "run" && run.id === activeRunId;
            return (
              <div
                key={run.id}
                onClick={() => onSelectRun(run.id)}
                className={`group flex cursor-pointer items-start gap-2 rounded-lg px-2 py-2 text-left transition-colors ${
                  isActive ? "bg-elevated" : "hover:bg-elevated/60"
                }`}
              >
                <div className="mt-1 shrink-0">
                  <Circle
                    size={7}
                    className={
                      visual.tone === "success"
                        ? "fill-success text-success"
                        : visual.tone === "danger"
                          ? "fill-danger text-danger"
                          : visual.tone === "warning"
                            ? "fill-warning text-warning"
                            : "fill-info text-info"
                    }
                  />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-xs font-medium text-primary">{run.repo}</div>
                  <div className="truncate text-[11px] text-tertiary">
                    {shortSha(run.baseCommit)} &middot; {formatRelativeTime(run.submittedAt)}
                  </div>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onRemoveRun(run.id);
                  }}
                  className="shrink-0 rounded p-0.5 text-tertiary opacity-0 hover:bg-overlay hover:text-primary group-hover:opacity-100"
                  aria-label="Remove run from history"
                >
                  <X size={12} />
                </button>
              </div>
            );
          })}
        </div>
      </div>

      <div className="border-t border-border-subtle px-5 py-3">
        <StatusPill
          tone={health === "ok" ? "success" : health === "down" ? "danger" : "neutral"}
          label={
            health === "ok" ? "Backend online" : health === "down" ? "Backend unreachable" : "Checking backend…"
          }
          size="sm"
          pulse={health === "checking"}
        />
      </div>
    </aside>
  );
}
