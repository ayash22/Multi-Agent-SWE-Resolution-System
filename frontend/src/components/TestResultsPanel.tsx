import { useState } from "react";

export interface CandidateForTests {
  candidate_id: string;
  source: string;
  tests_passed: string[];
  tests_failed: string[];
  is_selected: boolean;
  stdout?: string;
}

export default function TestResultsPanel({ candidates }: { candidates: CandidateForTests[] }) {
  const [activeId, setActiveId] = useState(candidates[0]?.candidate_id);
  const active = candidates.find((c) => c.candidate_id === activeId) ?? candidates[0];

  if (!candidates.length) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-900 p-5 text-slate-500 text-sm">
        No test results yet.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 p-5 space-y-3">
      <h2 className="text-lg font-semibold text-slate-100">Test Results</h2>

      <div className="flex gap-2 flex-wrap">
        {candidates.map((c) => (
          <button
            key={c.candidate_id}
            onClick={() => setActiveId(c.candidate_id)}
            className={`px-3 py-1.5 rounded-md text-xs font-medium border ${
              c.candidate_id === active?.candidate_id
                ? "border-indigo-500 bg-indigo-950 text-indigo-200"
                : "border-slate-700 bg-slate-800 text-slate-300"
            }`}
          >
            {c.source}
            {c.is_selected && (
              <span className="ml-2 rounded bg-emerald-600 text-white px-1.5 py-0.5 text-[10px]">
                SELECTED
              </span>
            )}
          </button>
        ))}
      </div>

      {active && (
        <>
          <div className="flex gap-4 text-sm">
            <span className="text-emerald-400">{active.tests_passed.length} passed</span>
            <span className="text-rose-400">{active.tests_failed.length} failed</span>
          </div>

          <div className="rounded-lg bg-black font-mono text-xs text-slate-200 p-3 h-64 overflow-y-auto whitespace-pre-wrap">
            {active.stdout || renderFallback(active)}
          </div>
        </>
      )}
    </div>
  );
}

function renderFallback(c: CandidateForTests): string {
  const lines = [
    ...c.tests_passed.map((t) => `${t} PASSED`),
    ...c.tests_failed.map((t) => `${t} FAILED`),
  ];
  return lines.join("\n") || "No pytest output captured for this candidate.";
}
