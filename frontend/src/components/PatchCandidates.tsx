export interface CandidateCard {
  candidate_id: string;
  source: string;
  rank_score: number | null;
  tests_passed: string[];
  tests_failed: string[];
  syntax_valid: boolean;
  applies_cleanly: boolean;
  is_selected: boolean;
}

function modelBadge(source: string) {
  if (source.startsWith("gpt4o")) {
    return <span className="text-xs px-2 py-0.5 rounded bg-sky-900 text-sky-300">GPT-4o</span>;
  }
  if (source.startsWith("llama3")) {
    return <span className="text-xs px-2 py-0.5 rounded bg-purple-900 text-purple-300">Llama-3 (fine-tuned)</span>;
  }
  return <span className="text-xs px-2 py-0.5 rounded bg-slate-700 text-slate-300">{source}</span>;
}

export default function PatchCandidates({ candidates }: { candidates: CandidateCard[] }) {
  if (!candidates.length) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-900 p-5 text-slate-500 text-sm">
        No candidates generated yet.
      </div>
    );
  }

  const sorted = [...candidates].sort((a, b) => (b.rank_score ?? -1) - (a.rank_score ?? -1));

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 p-5">
      <h2 className="text-lg font-semibold text-slate-100 mb-4">
        Best-of-{candidates.length} Candidates
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {sorted.map((c) => (
          <div
            key={c.candidate_id}
            className={`rounded-lg border p-3 space-y-2 ${
              c.is_selected ? "border-emerald-500 bg-emerald-950/30" : "border-slate-700 bg-slate-800"
            }`}
          >
            <div className="flex items-center justify-between">
              {modelBadge(c.source)}
              {c.is_selected && (
                <span className="text-[10px] rounded bg-emerald-600 text-white px-1.5 py-0.5">SELECTED</span>
              )}
            </div>
            <div className="text-sm text-slate-300">
              Score: {c.rank_score !== null ? c.rank_score.toFixed(3) : "—"}
            </div>
            <div className="flex gap-3 text-xs">
              <span className={c.syntax_valid ? "text-emerald-400" : "text-rose-400"}>
                syntax {c.syntax_valid ? "valid" : "invalid"}
              </span>
              <span className={c.applies_cleanly ? "text-emerald-400" : "text-rose-400"}>
                applies {c.applies_cleanly ? "cleanly" : "fails"}
              </span>
            </div>
            <div className="text-xs text-slate-400">
              {c.tests_passed.length} passed / {c.tests_failed.length} failed
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
