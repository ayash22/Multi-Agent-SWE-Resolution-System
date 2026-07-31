import { useState } from "react";
import {
  ArrowRight,
  ClipboardList,
  Code2,
  ListOrdered,
  Play,
  Search,
  ShieldCheck,
  TestTube2,
} from "lucide-react";
import TopBar from "../components/layout/TopBar";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import Tabs from "../components/ui/Tabs";
import { IssueSubmission } from "../lib/types";

const SWEBENCH_REPOS = [
  "django/django",
  "pytest-dev/pytest",
  "sympy/sympy",
  "psf/requests",
  "matplotlib/matplotlib",
  "scikit-learn/scikit-learn",
  "sphinx-doc/sphinx",
  "pylint-dev/pylint",
];

const STAGES = [
  { icon: ClipboardList, label: "Plan", detail: "GPT-4o reads the issue and drafts a fix strategy" },
  { icon: Search, label: "Retrieve", detail: "Hybrid FAISS + BM25 search over AST-chunked repo code" },
  { icon: Code2, label: "Code (×3)", detail: "2× GPT-4o + fine-tuned Llama-3 each generate a patch" },
  { icon: TestTube2, label: "Test (×3)", detail: "Each patch runs in an isolated, network-disabled Docker sandbox" },
  { icon: ShieldCheck, label: "Verify", detail: "Rejects gamed passes — requires a genuine, non-skipped test pass" },
  { icon: ListOrdered, label: "Rank", detail: "Learned best-of-N ranker selects the winning candidate" },
];

type InputMode = "url" | "paste";

export default function NewRunView({
  onSubmit,
  isSubmitting,
}: {
  onSubmit: (submission: IssueSubmission) => void;
  isSubmitting: boolean;
}) {
  const [mode, setMode] = useState<InputMode>("paste");
  const [repo, setRepo] = useState(SWEBENCH_REPOS[0]);
  const [baseCommit, setBaseCommit] = useState("");
  const [issueUrl, setIssueUrl] = useState("");
  const [issueText, setIssueText] = useState("");

  const canSubmit =
    repo.trim().length > 0 &&
    baseCommit.trim().length > 0 &&
    (mode === "url" ? issueUrl.trim().length > 0 : issueText.trim().length > 0);

  const shaLooksShort = baseCommit.trim().length > 0 && baseCommit.trim().length < 7;

  return (
    <>
      <TopBar title="New run" subtitle="Resolve a GitHub issue end-to-end" />
      <div className="flex-1 overflow-y-auto p-6">
        <div className="mx-auto grid max-w-5xl grid-cols-1 gap-6 lg:grid-cols-[1.1fr_0.9fr]">
          <Card title="Resolve a GitHub issue">
            <div className="space-y-4">
              <div>
                <label className="mb-1.5 block text-xs font-medium text-secondary">Repository</label>
                <input
                  list="swebench-repos"
                  className="w-full rounded-md border border-border bg-app px-3 py-2 text-sm text-primary placeholder:text-tertiary focus:border-accent focus:outline-none"
                  placeholder="owner/repo"
                  value={repo}
                  onChange={(e) => setRepo(e.target.value)}
                />
                <datalist id="swebench-repos">
                  {SWEBENCH_REPOS.map((r) => (
                    <option key={r} value={r} />
                  ))}
                </datalist>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-medium text-secondary">
                  Base commit SHA
                  <span className="ml-1.5 font-normal text-tertiary">— the commit the issue was opened against</span>
                </label>
                <input
                  className="w-full rounded-md border border-border bg-app px-3 py-2 font-mono text-sm text-primary placeholder:text-tertiary focus:border-accent focus:outline-none"
                  placeholder="e.g. e7fd69d051eaa67cb17f172a39b57253e9cb831a"
                  value={baseCommit}
                  onChange={(e) => setBaseCommit(e.target.value)}
                />
                {shaLooksShort && (
                  <p className="mt-1 text-[11px] text-warning">
                    That looks short for a commit SHA — double-check it against the repo's history.
                  </p>
                )}
              </div>

              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <label className="text-xs font-medium text-secondary">Issue</label>
                  <Tabs
                    items={[
                      { id: "paste", label: "Paste text" },
                      { id: "url", label: "GitHub URL" },
                    ]}
                    activeId={mode}
                    onChange={(id) => setMode(id as InputMode)}
                  />
                </div>
                {mode === "url" ? (
                  <input
                    className="w-full rounded-md border border-border bg-app px-3 py-2 text-sm text-primary placeholder:text-tertiary focus:border-accent focus:outline-none"
                    placeholder="https://github.com/django/django/issues/12345"
                    value={issueUrl}
                    onChange={(e) => setIssueUrl(e.target.value)}
                  />
                ) : (
                  <textarea
                    className="h-40 w-full resize-none rounded-md border border-border bg-app px-3 py-2 font-mono text-sm text-primary placeholder:text-tertiary focus:border-accent focus:outline-none"
                    placeholder="Paste the full issue title + body here..."
                    value={issueText}
                    onChange={(e) => setIssueText(e.target.value)}
                  />
                )}
              </div>

              <Button
                variant="primary"
                icon={isSubmitting ? undefined : Play}
                loading={isSubmitting}
                fullWidth
                disabled={!canSubmit}
                onClick={() =>
                  onSubmit({
                    repo,
                    baseCommit,
                    issueUrl: mode === "url" ? issueUrl : undefined,
                    issueText: mode === "paste" ? issueText : undefined,
                  })
                }
              >
                {isSubmitting ? "Running pipeline…" : "Resolve issue"}
              </Button>
            </div>
          </Card>

          <Card title="How this works">
            <div className="space-y-4">
              {STAGES.map((stage, i) => (
                <div key={stage.label} className="flex gap-3">
                  <div className="flex flex-col items-center">
                    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-elevated text-secondary">
                      <stage.icon size={13} />
                    </div>
                    {i < STAGES.length - 1 && <div className="mt-1 h-full w-px bg-border-subtle" />}
                  </div>
                  <div className="pb-4">
                    <div className="text-sm font-medium text-primary">{stage.label}</div>
                    <div className="text-xs text-tertiary">{stage.detail}</div>
                  </div>
                </div>
              ))}
              <div className="flex items-start gap-2 rounded-lg border border-border-subtle bg-app p-3 text-xs text-secondary">
                <ArrowRight size={13} className="mt-0.5 shrink-0 text-accent-hover" />
                Every candidate must pass <code className="text-primary">git apply --check</code> and a
                genuine (non-gamed) sandbox test pass before it can be selected.
              </div>
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
