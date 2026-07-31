import { useMemo, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Edge,
  Handle,
  Node,
  NodeProps,
  Position,
  ReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { deriveNodeStatuses, PIPELINE_EDGES, PIPELINE_NODES } from "../lib/pipeline";
import { nodeStatusVisual } from "../lib/status";
import { NodeStatus, RunResult } from "../lib/types";
import NodeInspector, { InspectedNode } from "./NodeInspector";
import StatusPill from "./ui/StatusPill";

const COL_WIDTH = 210;
const ROW_HEIGHT = 96;

interface FlowNodeData {
  label: string;
  status: NodeStatus;
  [key: string]: unknown;
}

function FlowNode({ data, selected }: NodeProps<Node<FlowNodeData>>) {
  const visual = nodeStatusVisual(data.status);
  return (
    <div
      className={`w-44 rounded-lg border bg-surface px-3 py-2.5 shadow-panel transition-colors ${
        selected ? "border-accent" : "border-border"
      }`}
    >
      <Handle type="target" position={Position.Left} className="!bg-tertiary" />
      <div className="truncate text-xs font-medium text-primary">{data.label}</div>
      <div className="mt-1.5">
        <StatusPill tone={visual.tone} label={visual.label} icon={visual.icon} pulse={visual.pulse} size="sm" />
      </div>
      <Handle type="source" position={Position.Right} className="!bg-tertiary" />
    </div>
  );
}

const nodeTypes = { pipelineNode: FlowNode };

export default function PipelineGraph({ result }: { result: RunResult | null }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const derived = useMemo(() => deriveNodeStatuses(result), [result]);

  const nodes: Node<FlowNodeData>[] = useMemo(
    () =>
      PIPELINE_NODES.map((spec) => ({
        id: spec.id,
        type: "pipelineNode",
        position: { x: spec.col * COL_WIDTH, y: spec.row * ROW_HEIGHT },
        data: { label: spec.label, status: derived[spec.id]?.status ?? "pending" },
        selected: spec.id === selectedId,
        draggable: false,
        connectable: false,
      })),
    [derived, selectedId]
  );

  const edges: Edge[] = useMemo(
    () =>
      PIPELINE_EDGES.map((e) => {
        const targetRunning = derived[e.target]?.status === "running";
        const sourceDone = derived[e.source]?.status === "done";
        return {
          id: `${e.source}->${e.target}`,
          source: e.source,
          target: e.target,
          animated: targetRunning,
          style: {
            stroke: sourceDone ? "var(--success)" : "var(--border-strong)",
            strokeWidth: 1.5,
          },
        };
      }),
    [derived]
  );

  const inspected: InspectedNode | null = useMemo(() => {
    if (!selectedId) return null;
    const spec = PIPELINE_NODES.find((n) => n.id === selectedId);
    if (!spec) return null;
    return {
      id: spec.id,
      label: spec.label,
      status: derived[spec.id]?.status ?? "pending",
      summary: derived[spec.id]?.summary,
    };
  }, [selectedId, derived]);

  return (
    <div className="flex h-[380px] overflow-hidden rounded-xl border border-border bg-surface">
      <div className="min-w-0 flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodeClick={(_, node) => setSelectedId(node.id)}
          onPaneClick={() => setSelectedId(null)}
          fitView
          fitViewOptions={{ padding: 0.25 }}
          nodesDraggable={false}
          nodesConnectable={false}
          zoomOnScroll={false}
          panOnScroll
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="var(--border-subtle)" />
        </ReactFlow>
      </div>
      <NodeInspector node={inspected} onClose={() => setSelectedId(null)} />
    </div>
  );
}
