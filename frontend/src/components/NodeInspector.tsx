import { X } from "lucide-react";
import { nodeStatusVisual } from "../lib/status";
import { NodeStatus } from "../lib/types";
import StatusPill from "./ui/StatusPill";

export interface InspectedNode {
  id: string;
  label: string;
  status: NodeStatus;
  summary?: string;
}

export default function NodeInspector({
  node,
  onClose,
}: {
  node: InspectedNode | null;
  onClose: () => void;
}) {
  if (!node) {
    return (
      <div className="flex h-full w-72 shrink-0 flex-col items-center justify-center border-l border-border-subtle px-6 text-center">
        <p className="text-xs text-tertiary">
          Click a node in the graph to inspect its status and output.
        </p>
      </div>
    );
  }

  const visual = nodeStatusVisual(node.status);

  return (
    <div className="flex h-full w-72 shrink-0 flex-col border-l border-border-subtle">
      <div className="flex items-center justify-between border-b border-border-subtle px-4 py-3">
        <span className="text-xs font-semibold uppercase tracking-wide text-tertiary">
          Node inspector
        </span>
        <button
          onClick={onClose}
          className="rounded p-0.5 text-tertiary hover:bg-elevated hover:text-primary"
          aria-label="Close inspector"
        >
          <X size={14} />
        </button>
      </div>
      <div className="space-y-4 px-4 py-4">
        <div>
          <div className="font-mono text-xs text-secondary">{node.id}</div>
          <div className="mt-0.5 text-sm font-semibold text-primary">{node.label}</div>
        </div>
        <StatusPill tone={visual.tone} label={visual.label} icon={visual.icon} pulse={visual.pulse} />
        {node.summary && (
          <div>
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-tertiary">
              Output
            </div>
            <div className="rounded-lg border border-border-subtle bg-app p-2.5 text-xs leading-relaxed text-secondary">
              {node.summary}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
