import { useMemo, useState } from "react";
import { Check, Copy, FileDiff } from "lucide-react";
import ReactDiffViewer, { DiffMethod } from "react-diff-viewer-continued";
import Button from "./ui/Button";
import Card from "./ui/Card";
import EmptyState from "./ui/EmptyState";
import Tabs from "./ui/Tabs";

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

function applyHunkToLines(hunk: string): { oldText: string; newText: string; added: number; removed: number } {
  const lines = hunk.split("\n");
  const oldLines: string[] = [];
  const newLines: string[] = [];
  let added = 0;
  let removed = 0;
  for (const line of lines) {
    if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("@@") || line.startsWith("diff --git")) {
      continue;
    }
    if (line.startsWith("+")) {
      newLines.push(line.slice(1));
      added++;
    } else if (line.startsWith("-")) {
      oldLines.push(line.slice(1));
      removed++;
    } else {
      oldLines.push(line.slice(1));
      newLines.push(line.slice(1));
    }
  }
  return { oldText: oldLines.join("\n"), newText: newLines.join("\n"), added, removed };
}

const diffViewerStyles = {
  variables: {
    light: {
      diffViewerBackground: "var(--bg-surface)",
      diffViewerColor: "var(--text-primary)",
      gutterBackground: "var(--bg-app)",
      addedBackground: "rgba(5, 150, 105, 0.08)",
      addedColor: "var(--text-primary)",
      removedBackground: "rgba(225, 29, 72, 0.08)",
      removedColor: "var(--text-primary)",
      wordAddedBackground: "rgba(5, 150, 105, 0.25)",
      wordRemovedBackground: "rgba(225, 29, 72, 0.25)",
      addedGutterBackground: "rgba(5, 150, 105, 0.08)",
      removedGutterBackground: "rgba(225, 29, 72, 0.08)",
      codeFoldBackground: "var(--bg-elevated)",
      emptyLineBackground: "var(--bg-surface)",
    },
  },
};

export default function CodeDiffViewer({ patchText }: { patchText: string }) {
  const [copied, setCopied] = useState(false);
  const [splitView, setSplitView] = useState(true);
  const files = useMemo(() => splitPatchByFile(patchText), [patchText]);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(patchText);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  if (!patchText) {
    return (
      <Card>
        <EmptyState icon={FileDiff} title="No patch generated yet" description="The selected candidate's diff will render here once a run completes." />
      </Card>
    );
  }

  return (
    <Card
      title="Generated patch"
      action={
        <div className="flex items-center gap-2">
          <Tabs
            items={[
              { id: "split", label: "Split" },
              { id: "unified", label: "Unified" },
            ]}
            activeId={splitView ? "split" : "unified"}
            onChange={(id) => setSplitView(id === "split")}
          />
          <Button size="sm" icon={copied ? Check : Copy} onClick={handleCopy}>
            {copied ? "Copied" : "Copy patch"}
          </Button>
        </div>
      }
      padded={false}
    >
      <div className="space-y-3 p-4">
        {files.map(({ filePath, hunk }) => {
          const { oldText, newText, added, removed } = applyHunkToLines(hunk);
          return (
            <div key={filePath} className="overflow-hidden rounded-lg border border-border-subtle">
              <div className="flex items-center justify-between bg-elevated px-3 py-1.5">
                <span className="truncate font-mono text-xs text-secondary">{filePath}</span>
                <span className="flex shrink-0 gap-2 font-mono text-[11px] tabular-nums">
                  <span className="text-success">+{added}</span>
                  <span className="text-danger">-{removed}</span>
                </span>
              </div>
              <ReactDiffViewer
                oldValue={oldText}
                newValue={newText}
                splitView={splitView}
                compareMethod={DiffMethod.LINES}
                useDarkTheme={false}
                showDiffOnly={true}
                styles={diffViewerStyles}
              />
            </div>
          );
        })}
      </div>
    </Card>
  );
}
