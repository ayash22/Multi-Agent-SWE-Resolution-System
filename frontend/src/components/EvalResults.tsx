import { useEffect, useState } from "react";

interface EvalSummary {
  baseline_resolved: number;
  full_system_resolved: number;
  total_instances: number;
  by_repo: Record<string, { baseline: number; full_system: number; total: number }>;
}

export default function EvalResults({ apiBaseUrl }: { apiBaseUrl: string }) {
  const [summary, setSummary] = useState<EvalSummary | null>(null);
  const [notRun, setNotRun] = useState(false);

  useEffect(() => {
    fetch(`${apiBaseUrl}/api/eval/summary`)
      .then(async (res) => {
        if (res.status === 404) {
          setNotRun(true);
          return;
        }
        setSummary(await res.json());
      })
      .catch(() => setNotRun(true));
  }, [apiBaseUrl]);

  if (notRun) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-900 p-5 text-slate-400 text-sm">
        <h2 className="text-lg font-semibold text-slate-100 mb-2">SWE-bench Lite Score</h2>
        No evaluation run has completed yet. Run{" "}
        <code className="bg-slate-800 px-1.5 py-0.5 rounded">evaluation/run_swebench_eval.py</code>{" "}
        against the 90-instance sample to populate this panel with real, harness-graded results.
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-900 p-5 text-slate-500 text-sm">
        Loading evaluation summary...
      </div>
    );
  }

  const pct = (n: number) => ((100 * n) / summary.total_instances).toFixed(1);

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 p-5 space-y-4">
      <h2 className="text-lg font-semibold text-slate-100">SWE-bench Lite Score</h2>
      <div className="flex gap-6">
        <div>
          <div className="text-xs text-slate-500">Baseline (single-shot)</div>
          <div className="text-2xl font-bold text-slate-200">
            {summary.baseline_resolved}/{summary.total_instances}{" "}
            <span className="text-sm text-slate-400">({pct(summary.baseline_resolved)}%)</span>
          </div>
        </div>
        <div>
          <div className="text-xs text-slate-500">Full system (best-of-N + self-correction)</div>
          <div className="text-2xl font-bold text-emerald-400">
            {summary.full_system_resolved}/{summary.total_instances}{" "}
            <span className="text-sm text-slate-400">({pct(summary.full_system_resolved)}%)</span>
          </div>
        </div>
      </div>

      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-slate-500 border-b border-slate-800">
            <th className="py-1">Repo</th>
            <th className="py-1">Total</th>
            <th className="py-1">Baseline</th>
            <th className="py-1">Full system</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(summary.by_repo).map(([repo, stats]) => (
            <tr key={repo} className="border-b border-slate-800/50 text-slate-300">
              <td className="py-1 font-mono text-xs">{repo}</td>
              <td className="py-1">{stats.total}</td>
              <td className="py-1">{stats.baseline}</td>
              <td className="py-1">{stats.full_system}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
