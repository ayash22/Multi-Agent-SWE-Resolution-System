import { useState } from "react";

export type StepStatus = "pending" | "running" | "done" | "failed";

export interface PipelineStep {
  step: string;
  status: StepStatus;
  input_summary?: string;
  output_summary?: string;
}

const STAGE_GROUPS: { label: string; steps: string[] }[] = [
  { label: "Plan", steps: ["planner"] },
  { label: "Retrieve", steps: ["retrieval"] },
  { label: "Code (x3)", steps: ["coder_gpt4o_run1", "coder_gpt4o_run2", "llama_coder"] },
  { label: "Test (x3)", steps: ["test_runner_run1", "test_runner_run2", "test_runner_llama"] },
  { label: "Verify", steps: ["verifier"] },
  { label: "Rank", steps: ["patch_ranker"] },
];

const STATUS_COLOR: Record<StepStatus, string> = {
  pending: "bg-slate-700 text-slate-400",
  running: "bg-amber-500 text-slate-900 animate-pulse",
  done: "bg-emerald-500 text-slate-900",
  failed: "bg-rose-600 text-white",
};

export default function AgentPipelineViz({ steps }: { steps: PipelineStep[] }) {
  const [selected, setSelected] = useState<PipelineStep | null>(null);
  const byName = Object.fromEntries(steps.map((s) => [s.step, s]));

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 p-5">
      <h2 className="text-lg font-semibold text-slate-100 mb-4">Agent Pipeline</h2>
      <div className="flex flex-wrap items-center gap-2">
        {STAGE_GROUPS.map((group, i) => (
          <div key={group.label} className="flex items-center gap-2">
            <div className="flex flex-col gap-1">
              <span className="text-xs text-slate-500">{group.label}</span>
              <div className="flex gap-1">
                {group.steps.map((stepName) => {
                  const step = byName[stepName] ?? { step: stepName, status: "pending" as StepStatus };
                  return (
                    <button
                      key={stepName}
                      onClick={() => setSelected(step)}
                      className={`px-2.5 py-1.5 rounded-md text-xs font-medium ${STATUS_COLOR[step.status]}`}
                      title={stepName}
                    >
                      {stepName.replace(/_/g, " ")}
                    </button>
                  );
                })}
              </div>
            </div>
            {i < STAGE_GROUPS.length - 1 && <span className="text-slate-600">→</span>}
          </div>
        ))}
      </div>

      {selected && (
        <div className="mt-4 rounded-lg border border-slate-700 bg-slate-800 p-3 text-sm">
          <div className="font-mono text-slate-300 mb-1">{selected.step}</div>
          <div className="text-slate-400">Status: {selected.status}</div>
          {selected.input_summary && (
            <div className="mt-1 text-slate-400">Input: {selected.input_summary}</div>
          )}
          {selected.output_summary && (
            <div className="mt-1 text-slate-400">Output: {selected.output_summary}</div>
          )}
        </div>
      )}
    </div>
  );
}
