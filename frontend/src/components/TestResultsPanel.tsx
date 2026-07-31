import { useState } from "react";
import { TerminalSquare } from "lucide-react";
import Card from "./ui/Card";
import EmptyState from "./ui/EmptyState";
import Tabs from "./ui/Tabs";

export interface CandidateForTests {
  candidate_id: string;
  source: string;
  tests_passed: string[];
  tests_failed: string[];
  is_selected: boolean;
  stdout?: string;
}

function renderFallback(c: CandidateForTests): string {
  const lines = [
    ...c.tests_passed.map((t) => `PASSED  ${t}`),
    ...c.tests_failed.map((t) => `FAILED  ${t}`),
  ];
  return lines.join("\n") || "No pytest output captured for this candidate.";
}

function ConsoleLine({ line }: { line: string }) {
  if (line.startsWith("PASSED")) return <div className="text-success">{line}</div>;
  if (line.startsWith("FAILED")) return <div className="text-danger">{line}</div>;
  return <div className="text-secondary">{line}</div>;
}

export default function TestResultsPanel({ candidates }: { candidates: CandidateForTests[] }) {
  const [activeId, setActiveId] = useState(candidates[0]?.candidate_id);
  const active = candidates.find((c) => c.candidate_id === activeId) ?? candidates[0];

  if (!candidates.length) {
    return (
      <Card>
        <EmptyState icon={TerminalSquare} title="No test results yet" description="Sandbox test output for each candidate will appear here." />
      </Card>
    );
  }

  return (
    <Card
      title="Test results"
      action={
        <Tabs
          items={candidates.map((c) => ({
            id: c.candidate_id,
            label: c.source,
            badge: c.is_selected ? (
              <span className="ml-1 rounded bg-success-muted px-1 py-0.5 text-[9px] font-semibold text-success">
                SELECTED
              </span>
            ) : undefined,
          }))}
          activeId={active?.candidate_id ?? ""}
          onChange={setActiveId}
        />
      }
    >
      {active && (
        <div className="space-y-3">
          <div className="flex gap-4 text-sm">
            <span className="text-success">{active.tests_passed.length} passed</span>
            <span className="text-danger">{active.tests_failed.length} failed</span>
          </div>

          <div className="overflow-hidden rounded-lg border border-border-subtle">
            <div className="flex items-center gap-1.5 bg-elevated px-3 py-2">
              <span className="h-2.5 w-2.5 rounded-full bg-danger/60" />
              <span className="h-2.5 w-2.5 rounded-full bg-warning/60" />
              <span className="h-2.5 w-2.5 rounded-full bg-success/60" />
              <span className="ml-2 font-mono text-[11px] text-tertiary">pytest — {active.source}</span>
            </div>
            <div className="h-64 overflow-y-auto whitespace-pre-wrap bg-app p-3 font-mono text-xs leading-relaxed">
              {(active.stdout || renderFallback(active)).split("\n").map((line, i) => (
                <ConsoleLine key={i} line={line} />
              ))}
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
