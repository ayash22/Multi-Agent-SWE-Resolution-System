import { useState } from "react";
import IssueInput, { IssueSubmission } from "./components/IssueInput";
import AgentPipelineViz, { PipelineStep } from "./components/AgentPipelineViz";
import CodeDiffViewer from "./components/CodeDiffViewer";
import TestResultsPanel from "./components/TestResultsPanel";
import PatchCandidates from "./components/PatchCandidates";
import EvalResults from "./components/EvalResults";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

interface RunResult {
  status: string;
  pipeline_steps: PipelineStep[];
  final_patch: string | null;
  resolved: boolean | null;
  explanation: string | null;
  candidates: {
    candidate_id: string;
    source: string;
    patch_text: string;
    syntax_valid: boolean;
    applies_cleanly: boolean;
    tests_passed: string[];
    tests_failed: string[];
    rank_score: number | null;
    is_selected: boolean;
  }[];
}

export default function App() {
  const [result, setResult] = useState<RunResult | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (submission: IssueSubmission) => {
    setIsSubmitting(true);
    setError(null);
    setResult(null);
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
      setResult(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setIsSubmitting(false);
    }
  };

  const selectedPatch = result?.candidates.find((c) => c.is_selected)?.patch_text
    ?? result?.final_patch
    ?? "";

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6 space-y-6 max-w-6xl mx-auto">
      <header>
        <h1 className="text-2xl font-bold">Multi-Agent SWE-bench Resolution System</h1>
        <p className="text-slate-400 text-sm mt-1">
          GPT-4o + fine-tuned Llama-3 · hybrid retrieval · Docker-sandboxed test execution · best-of-N ranking
        </p>
      </header>

      <IssueInput onSubmit={handleSubmit} isSubmitting={isSubmitting} />

      {error && (
        <div className="rounded-lg border border-rose-800 bg-rose-950/40 text-rose-300 p-3 text-sm">
          {error}
        </div>
      )}

      {result && (
        <>
          <AgentPipelineViz steps={result.pipeline_steps} />

          {result.explanation && (
            <div
              className={`rounded-lg p-3 text-sm border ${
                result.resolved
                  ? "border-emerald-800 bg-emerald-950/30 text-emerald-300"
                  : "border-amber-800 bg-amber-950/30 text-amber-300"
              }`}
            >
              {result.explanation}
            </div>
          )}

          <PatchCandidates candidates={result.candidates} />
          <CodeDiffViewer patchText={selectedPatch} />
          <TestResultsPanel candidates={result.candidates} />
        </>
      )}

      <EvalResults apiBaseUrl={API_BASE_URL} />
    </div>
  );
}
