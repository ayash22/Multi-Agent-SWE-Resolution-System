import { useMemo, useState } from "react";
import ReactDiffViewer, { DiffMethod } from "react-diff-viewer-continued";

/**
 * Parses a unified diff string into (oldContent, newContent, filePath) so it
 * can be rendered with react-diff-viewer's side-by-side view. Handles the
 * common single-file-per-hunk-block case produced by our coder agents; for
 * multi-file patches, splits on `diff --git` / `--- a/` boundaries and
 * renders one viewer per file.
 */
function splitPatchByFile(patch: string): { filePath: string; hunk: string }[] {
  const blocks = patch.split(/(?=^--- a\/)/m).filter((b) => b.trim());
  return blocks.map((block) => {
    const match = block.match(/^--- a\/(.+)$/m);
    return { filePath: match ? match[1] : "unknown file", hunk: block };
  });
}

function applyHunkToLines(hunk: string): { oldText: string; newText: string } {
  const lines = hunk.split("\n");
  const oldLines: string[] = [];
  const newLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("@@") || line.startsWith("diff --git")) {
      continue;
    }
    if (line.startsWith("+")) newLines.push(line.slice(1));
    else if (line.startsWith("-")) oldLines.push(line.slice(1));
    else {
      oldLines.push(line.slice(1));
      newLines.push(line.slice(1));
    }
  }
  return { oldText: oldLines.join("\n"), newText: newLines.join("\n") };
}

export default function CodeDiffViewer({ patchText }: { patchText: string }) {
  const [copied, setCopied] = useState(false);
  const files = useMemo(() => splitPatchByFile(patchText), [patchText]);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(patchText);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  if (!patchText) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-900 p-5 text-slate-500 text-sm">
        No patch generated yet.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-100">Generated Patch</h2>
        <button
          onClick={handleCopy}
          className="text-xs px-3 py-1.5 rounded-md bg-slate-800 text-slate-200 hover:bg-slate-700"
        >
          {copied ? "Copied!" : "Copy patch"}
        </button>
      </div>

      {files.map(({ filePath, hunk }) => {
        const { oldText, newText } = applyHunkToLines(hunk);
        return (
          <div key={filePath} className="rounded-lg overflow-hidden border border-slate-700">
            <div className="bg-slate-800 px-3 py-1.5 text-sm font-mono text-slate-300">
              {filePath}
            </div>
            <ReactDiffViewer
              oldValue={oldText}
              newValue={newText}
              splitView={true}
              compareMethod={DiffMethod.LINES}
              useDarkTheme={true}
              showDiffOnly={true}
            />
          </div>
        );
      })}
    </div>
  );
}
