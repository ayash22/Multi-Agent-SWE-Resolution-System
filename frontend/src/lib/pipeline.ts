import { NodeStatus, RunResult } from "./types";

/** Static topology mirroring agents/graph.py's build_graph(): planner ->
 * retrieval -> fan-out to 3 coders -> matching 3 test runners -> fan-in
 * verifier -> patch_ranker. Columns/rows are layout hints for PipelineGraph. */
export interface PipelineNodeSpec {
  id: string;
  label: string;
  col: number;
  row: number;
  /** candidate_id in RunResult.candidates this node's real outcome is
   * derived from, for coder_* / test_runner_* nodes. */
  candidateId?: string;
}

export const PIPELINE_NODES: PipelineNodeSpec[] = [
  { id: "planner", label: "Planner", col: 0, row: 1 },
  { id: "retrieval", label: "Retrieval", col: 1, row: 1 },
  { id: "coder_gpt4o_run1", label: "Coder · GPT-4o run1", col: 2, row: 0, candidateId: "gpt4o_run1" },
  { id: "coder_gpt4o_run2", label: "Coder · GPT-4o run2", col: 2, row: 1, candidateId: "gpt4o_run2" },
  { id: "llama_coder", label: "Coder · Llama-3", col: 2, row: 2, candidateId: "llama3_coder" },
  { id: "test_runner_run1", label: "Test · run1", col: 3, row: 0, candidateId: "gpt4o_run1" },
  { id: "test_runner_run2", label: "Test · run2", col: 3, row: 1, candidateId: "gpt4o_run2" },
  { id: "test_runner_llama", label: "Test · llama", col: 3, row: 2, candidateId: "llama3_coder" },
  { id: "verifier", label: "Verifier", col: 4, row: 1 },
  { id: "patch_ranker", label: "Ranker", col: 5, row: 1 },
];

export const PIPELINE_EDGES: { source: string; target: string }[] = [
  { source: "planner", target: "retrieval" },
  { source: "retrieval", target: "coder_gpt4o_run1" },
  { source: "retrieval", target: "coder_gpt4o_run2" },
  { source: "retrieval", target: "llama_coder" },
  { source: "coder_gpt4o_run1", target: "test_runner_run1" },
  { source: "coder_gpt4o_run2", target: "test_runner_run2" },
  { source: "llama_coder", target: "test_runner_llama" },
  { source: "test_runner_run1", target: "verifier" },
  { source: "test_runner_run2", target: "verifier" },
  { source: "test_runner_llama", target: "verifier" },
  { source: "verifier", target: "patch_ranker" },
];

export interface DerivedNode {
  status: NodeStatus;
  summary?: string;
}

/** Backend's IssueRunResponse.pipeline_steps currently always reports every
 * step as "done" with no summaries (serving/app/issue_handler.py builds it
 * from a static list post-hoc). We derive richer, real per-node status from
 * the actual data the response does carry -- the plan, retrieved chunks, and
 * per-candidate test outcomes -- so the graph reflects what genuinely
 * happened rather than a flat "everything done". */
export function deriveNodeStatuses(result: RunResult | null): Record<string, DerivedNode> {
  const out: Record<string, DerivedNode> = {};
  if (!result) {
    for (const n of PIPELINE_NODES) out[n.id] = { status: "pending" };
    return out;
  }

  const stepByName = new Map(result.pipeline_steps.map((s) => [s.step, s]));
  const candidateById = new Map(result.candidates.map((c) => [c.candidate_id, c]));

  for (const n of PIPELINE_NODES) {
    const backendStep = stepByName.get(n.id);
    let status: NodeStatus = backendStep?.status ?? "pending";
    let summary: string | undefined = backendStep?.output_summary ?? undefined;

    if (n.candidateId) {
      const candidate = candidateById.get(n.candidateId);
      if (!candidate) {
        status = "pending";
      } else if (n.id.startsWith("coder_") || n.id === "llama_coder") {
        status = "done";
        summary = candidate.syntax_valid
          ? candidate.applies_cleanly
            ? "Syntax valid, applies cleanly"
            : "Syntax valid, does not apply"
          : "Syntax invalid / rejected";
      } else if (n.id.startsWith("test_runner")) {
        const ran = candidate.tests_passed.length + candidate.tests_failed.length > 0;
        status = ran ? "done" : "pending";
        summary = ran
          ? `${candidate.tests_passed.length} passed / ${candidate.tests_failed.length} failed`
          : "Skipped (patch did not apply)";
      }
    } else if (n.id === "planner" && result.plan) {
      status = "done";
      summary = String(result.plan.issue_summary ?? "");
    } else if (n.id === "retrieval") {
      status = result.retrieved_chunks.length > 0 ? "done" : status;
      summary = `${result.retrieved_chunks.length} chunk${result.retrieved_chunks.length === 1 ? "" : "s"} retrieved`;
    } else if (n.id === "verifier") {
      status = result.candidates.length > 0 ? "done" : status;
      summary = `${result.candidates.length} candidate${result.candidates.length === 1 ? "" : "s"} reconciled`;
    } else if (n.id === "patch_ranker") {
      status = result.candidates.some((c) => c.is_selected) || result.final_patch ? "done" : status;
      summary = result.explanation ?? summary;
    }

    out[n.id] = { status, summary };
  }
  return out;
}
