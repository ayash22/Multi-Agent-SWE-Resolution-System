import { useState } from "react";
import AppShell from "./components/layout/AppShell";
import { ViewId } from "./components/layout/Sidebar";
import { useBackendHealth } from "./lib/health";
import { useRunHistory } from "./lib/runs";
import { IssueSubmission, RunResult } from "./lib/types";
import EvalView from "./views/EvalView";
import NewRunView from "./views/NewRunView";
import RunView from "./views/RunView";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export default function App() {
  const [view, setView] = useState<ViewId>("new");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { runs, startRun, completeRun, removeRun } = useRunHistory();
  const health = useBackendHealth(API_BASE_URL);

  const activeRun = runs.find((r) => r.id === activeRunId) ?? null;

  const handleSubmit = async (submission: IssueSubmission) => {
    const issuePreview = submission.issueUrl ?? (submission.issueText ?? "").slice(0, 80);
    const id = startRun(submission.repo, submission.baseCommit, issuePreview);
    setActiveRunId(id);
    setView("run");
    setIsSubmitting(true);

    try {
      const res = await fetch(`${API_BASE_URL}/api/issues/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repo: submission.repo,
          base_commit: submission.baseCommit,
          issue_url: submission.issueUrl,
          issue_text: submission.issueText,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `Request failed (${res.status})`);
      }
      const result: RunResult = await res.json();
      completeRun(id, {
        result,
        outcome: result.resolved ? "resolved" : "unresolved",
        completedAt: Date.now(),
      });
    } catch (e) {
      completeRun(id, {
        outcome: "error",
        errorMessage: e instanceof Error ? e.message : String(e),
        completedAt: Date.now(),
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSelectRun = (id: string) => {
    setActiveRunId(id);
    setView("run");
  };

  const handleRemoveRun = (id: string) => {
    removeRun(id);
    if (activeRunId === id) {
      setActiveRunId(null);
      setView("new");
    }
  };

  return (
    <AppShell
      view={view}
      onNavigate={setView}
      runs={runs}
      activeRunId={activeRunId}
      onSelectRun={handleSelectRun}
      onRemoveRun={handleRemoveRun}
      health={health}
    >
      {view === "new" && <NewRunView onSubmit={handleSubmit} isSubmitting={isSubmitting} />}
      {view === "run" && activeRun && <RunView run={activeRun} />}
      {view === "run" && !activeRun && <NewRunView onSubmit={handleSubmit} isSubmitting={isSubmitting} />}
      {view === "eval" && <EvalView apiBaseUrl={API_BASE_URL} />}
    </AppShell>
  );
}
