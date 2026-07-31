import { Copy } from "lucide-react";
import PipelineGraph from "../components/PipelineGraph";
import CodeDiffViewer from "../components/CodeDiffViewer";
import PatchCandidates from "../components/PatchCandidates";
import TestResultsPanel from "../components/TestResultsPanel";
import TopBar from "../components/layout/TopBar";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import StatusPill from "../components/ui/StatusPill";
import { formatDuration, shortSha } from "../lib/format";
import { runOutcomeVisual } from "../lib/status";
import { RunRecord } from "../lib/types";

export default function RunView({ run }: { run: RunRecord }) {
  const visual = runOutcomeVisual(run.outcome);
  const result = run.result;
  const selectedPatch = result?.candidates.find((c) => c.is_selected)?.patch_text ?? result?.final_patch ?? "";

  const handleCopyPatch = () => {
    if (selectedPatch) navigator.clipboard.writeText(selectedPatch);
  };

  return (
    <>
      <TopBar
        title={
          <span className="flex items-center gap-2">
            {run.repo}
            <Badge tone="neutral">{shortSha(run.baseCommit)}</Badge>
          </span>
        }
        subtitle={result?.instance_id ?? run.issuePreview}
        action={
          <>
            {run.completedAt && (
              <span className="text-xs text-tertiary">
                {formatDuration(run.completedAt - run.submittedAt)}
              </span>
            )}
            <StatusPill tone={visual.tone} label={visual.label} icon={visual.icon} pulse={visual.pulse} />
            {selectedPatch && <Button size="sm" icon={Copy} onClick={handleCopyPatch}>Copy patch</Button>}
          </>
        }
      />
      <div className="flex-1 space-y-5 overflow-y-auto p-6">
        {run.outcome === "error" && (
          <div className="rounded-lg border border-danger/30 bg-danger-muted p-3.5 text-sm text-danger">
            {run.errorMessage ?? "The pipeline request failed."}
          </div>
        )}

        <PipelineGraph result={result} />

        {result?.explanation && (
          <div
            className={`rounded-lg border p-3.5 text-sm ${
              result.resolved
                ? "border-success/30 bg-success-muted text-success"
                : "border-warning/30 bg-warning-muted text-warning"
            }`}
          >
            {result.explanation}
          </div>
        )}

        {result && (
          <>
            <PatchCandidates candidates={result.candidates} />
            <CodeDiffViewer patchText={selectedPatch} />
            <TestResultsPanel candidates={result.candidates} />
          </>
        )}
      </div>
    </>
  );
}
