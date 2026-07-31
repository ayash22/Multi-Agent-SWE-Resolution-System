import { useEffect, useState } from "react";
import { ArrowUpRight, BarChart3, Loader2 } from "lucide-react";
import TopBar from "../components/layout/TopBar";
import Card from "../components/ui/Card";
import EmptyState from "../components/ui/EmptyState";

interface EvalSummary {
  baseline_resolved: number;
  full_system_resolved: number;
  total_instances: number;
  by_repo: Record<string, { baseline: number; full_system: number; total: number }>;
}

function StatTile({ label, value, sub, tone }: { label: string; value: string; sub: string; tone: "neutral" | "accent" }) {
  return (
    <div className="flex-1 rounded-xl border border-border bg-surface p-4">
      <div className="text-xs text-tertiary">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${tone === "accent" ? "text-accent-hover" : "text-primary"}`}>
        {value}
      </div>
      <div className="mt-0.5 text-xs text-secondary">{sub}</div>
    </div>
  );
}

function RepoBarRow({ repo, stats }: { repo: string; stats: { baseline: number; full_system: number; total: number } }) {
  const baselinePct = stats.total > 0 ? (100 * stats.baseline) / stats.total : 0;
  const fullPct = stats.total > 0 ? (100 * stats.full_system) / stats.total : 0;
  return (
    <div className="py-2.5">
      <div className="mb-1.5 flex items-center justify-between text-xs">
        <span className="font-mono text-secondary">{repo}</span>
        <span className="text-tertiary">
          {stats.baseline}/{stats.total} → {stats.full_system}/{stats.total}
        </span>
      </div>
      <div className="space-y-1">
        <div className="h-2 w-full overflow-hidden rounded-full bg-app">
          <div className="h-full rounded-full bg-tertiary" style={{ width: `${baselinePct}%` }} />
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-app">
          <div className="h-full rounded-full bg-accent" style={{ width: `${fullPct}%` }} />
        </div>
      </div>
    </div>
  );
}

export default function EvalView({ apiBaseUrl }: { apiBaseUrl: string }) {
  const [summary, setSummary] = useState<EvalSummary | null>(null);
  const [notRun, setNotRun] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`${apiBaseUrl}/api/eval/summary`)
      .then(async (res) => {
        if (res.status === 404) {
          setNotRun(true);
          return;
        }
        setSummary(await res.json());
      })
      .catch(() => setNotRun(true))
      .finally(() => setLoading(false));
  }, [apiBaseUrl]);

  return (
    <>
      <TopBar title="Evaluation" subtitle="SWE-bench Lite — official harness results" />
      <div className="flex-1 overflow-y-auto p-6">
        <div className="mx-auto max-w-4xl space-y-5">
          {loading && (
            <div className="flex items-center gap-2 py-10 text-sm text-tertiary">
              <Loader2 size={14} className="animate-spin" /> Loading evaluation summary…
            </div>
          )}

          {!loading && notRun && (
            <Card>
              <EmptyState icon={BarChart3} title="No evaluation run has completed yet">
                <div className="mt-2 rounded-lg border border-border-subtle bg-app px-3 py-2 font-mono text-xs text-secondary">
                  python evaluation/run_swebench_eval.py report ...
                </div>
                <p className="mt-2 max-w-sm text-xs text-tertiary">
                  Run the 90-instance sample against the baseline and full-system configs to populate
                  this view with real, harness-graded results.
                </p>
              </EmptyState>
            </Card>
          )}

          {!loading && summary && (
            <>
              <div className="flex gap-4">
                <StatTile
                  label="Baseline (single-shot)"
                  value={`${summary.baseline_resolved}/${summary.total_instances}`}
                  sub={`${((100 * summary.baseline_resolved) / summary.total_instances).toFixed(1)}% resolved`}
                  tone="neutral"
                />
                <StatTile
                  label="Full system (best-of-N + retries)"
                  value={`${summary.full_system_resolved}/${summary.total_instances}`}
                  sub={`${((100 * summary.full_system_resolved) / summary.total_instances).toFixed(1)}% resolved`}
                  tone="accent"
                />
                <div className="flex flex-1 flex-col items-center justify-center rounded-xl border border-success/30 bg-success-muted p-4">
                  <ArrowUpRight size={16} className="text-success" />
                  <div className="mt-1 text-2xl font-semibold tabular-nums text-success">
                    +{summary.full_system_resolved - summary.baseline_resolved}
                  </div>
                  <div className="text-xs text-success/80">instances improved</div>
                </div>
              </div>

              <Card title="Resolved rate by repository">
                <div className="mb-3 flex items-center gap-4 text-xs text-tertiary">
                  <span className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-tertiary" /> Baseline
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-accent" /> Full system
                  </span>
                </div>
                <div className="divide-y divide-border-subtle">
                  {Object.entries(summary.by_repo).map(([repo, stats]) => (
                    <RepoBarRow key={repo} repo={repo} stats={stats} />
                  ))}
                </div>
              </Card>
            </>
          )}
        </div>
      </div>
    </>
  );
}
