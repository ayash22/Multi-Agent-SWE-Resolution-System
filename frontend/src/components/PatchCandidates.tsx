import { CheckCircle2, Cpu, Sparkles, XCircle } from "lucide-react";
import Badge from "./ui/Badge";
import Card from "./ui/Card";
import EmptyState from "./ui/EmptyState";

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

function ModelBadge({ source }: { source: string }) {
  if (source.startsWith("gpt4o")) {
    return (
      <Badge tone="info" icon={Sparkles}>
        GPT-4o {source.endsWith("run2") ? "· T=0.6" : "· T=0.1"}
      </Badge>
    );
  }
  if (source.startsWith("llama3")) {
    return (
      <Badge tone="accent" icon={Cpu}>
        {source === "llama3_finetuned" ? "Llama-3 (fine-tuned)" : "Llama-3 (base fallback)"}
      </Badge>
    );
  }
  return <Badge tone="neutral">{source}</Badge>;
}

function CheckRow({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className={`flex items-center gap-1.5 text-xs ${ok ? "text-success" : "text-danger"}`}>
      {ok ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
      {label}
    </div>
  );
}

export default function PatchCandidates({ candidates }: { candidates: CandidateCard[] }) {
  if (!candidates.length) {
    return (
      <Card>
        <EmptyState icon={Sparkles} title="No candidates yet" description="Patch candidates will appear here once the coder agents finish generating." />
      </Card>
    );
  }

  const sorted = [...candidates].sort((a, b) => (b.rank_score ?? -1) - (a.rank_score ?? -1));
  const maxScore = Math.max(0.01, ...sorted.map((c) => c.rank_score ?? 0));

  return (
    <Card title={`Best-of-${candidates.length} candidates`}>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {sorted.map((c) => (
          <div
            key={c.candidate_id}
            className={`space-y-3 rounded-lg border p-3.5 ${
              c.is_selected ? "border-accent bg-accent-muted/40" : "border-border-subtle bg-elevated/40"
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <ModelBadge source={c.source} />
              {c.is_selected && (
                <span className="inline-flex shrink-0 items-center gap-1 rounded bg-success-muted px-1.5 py-0.5 text-[10px] font-semibold text-success">
                  <CheckCircle2 size={11} /> SELECTED
                </span>
              )}
            </div>

            <div>
              <div className="mb-1 flex items-baseline justify-between text-xs">
                <span className="text-tertiary">Rank score</span>
                <span className="font-mono tabular-nums text-secondary">
                  {c.rank_score !== null ? c.rank_score.toFixed(3) : "—"}
                </span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-app">
                <div
                  className={`h-full rounded-full ${c.is_selected ? "bg-accent" : "bg-tertiary"}`}
                  style={{ width: `${Math.min(100, ((c.rank_score ?? 0) / maxScore) * 100)}%` }}
                />
              </div>
            </div>

            <div className="space-y-1">
              <CheckRow label={c.syntax_valid ? "Syntax valid" : "Syntax invalid"} ok={c.syntax_valid} />
              <CheckRow label={c.applies_cleanly ? "Applies cleanly" : "Fails to apply"} ok={c.applies_cleanly} />
            </div>

            <div className="flex gap-3 border-t border-border-subtle pt-2.5 text-xs">
              <span className="text-success">{c.tests_passed.length} passed</span>
              <span className="text-danger">{c.tests_failed.length} failed</span>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
