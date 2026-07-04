import { useState } from "react";

export interface IssueSubmission {
  repo: string;
  issueUrl?: string;
  issueText?: string;
  baseCommit: string;
}

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

type InputMode = "url" | "paste";

export default function IssueInput({
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
    baseCommit.trim().length > 0 &&
    (mode === "url" ? issueUrl.trim().length > 0 : issueText.trim().length > 0);

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 p-5 space-y-4">
      <h2 className="text-lg font-semibold text-slate-100">Resolve a GitHub Issue</h2>

      <div>
        <label className="block text-sm text-slate-400 mb-1">Repository</label>
        <select
          className="w-full rounded-md bg-slate-800 border border-slate-700 px-3 py-2 text-slate-100"
          value={repo}
          onChange={(e) => setRepo(e.target.value)}
        >
          {SWEBENCH_REPOS.map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
      </div>

      <div>
        <label className="block text-sm text-slate-400 mb-1">
          Base commit SHA (the commit the issue was opened against)
        </label>
        <input
          className="w-full rounded-md bg-slate-800 border border-slate-700 px-3 py-2 text-slate-100 font-mono text-sm"
          placeholder="e.g. 3b3c1e..."
          value={baseCommit}
          onChange={(e) => setBaseCommit(e.target.value)}
        />
      </div>

      <div className="flex gap-2">
        <button
          className={`px-3 py-1.5 rounded-md text-sm ${mode === "paste" ? "bg-indigo-600 text-white" : "bg-slate-800 text-slate-300"}`}
          onClick={() => setMode("paste")}
        >
          Paste issue text
        </button>
        <button
          className={`px-3 py-1.5 rounded-md text-sm ${mode === "url" ? "bg-indigo-600 text-white" : "bg-slate-800 text-slate-300"}`}
          onClick={() => setMode("url")}
        >
          GitHub issue URL
        </button>
      </div>

      {mode === "url" ? (
        <input
          className="w-full rounded-md bg-slate-800 border border-slate-700 px-3 py-2 text-slate-100"
          placeholder="https://github.com/django/django/issues/12345"
          value={issueUrl}
          onChange={(e) => setIssueUrl(e.target.value)}
        />
      ) : (
        <textarea
          className="w-full h-40 rounded-md bg-slate-800 border border-slate-700 px-3 py-2 text-slate-100 font-mono text-sm"
          placeholder="Paste the full issue text here..."
          value={issueText}
          onChange={(e) => setIssueText(e.target.value)}
        />
      )}

      <button
        disabled={!canSubmit || isSubmitting}
        onClick={() =>
          onSubmit({
            repo,
            baseCommit,
            issueUrl: mode === "url" ? issueUrl : undefined,
            issueText: mode === "paste" ? issueText : undefined,
          })
        }
        className="w-full rounded-md bg-indigo-600 disabled:bg-slate-700 disabled:text-slate-500 text-white py-2 font-medium"
      >
        {isSubmitting ? "Running pipeline..." : "Resolve Issue"}
      </button>
    </div>
  );
}
