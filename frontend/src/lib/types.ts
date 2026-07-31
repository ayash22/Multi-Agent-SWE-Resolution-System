export type NodeStatus = "pending" | "running" | "done" | "failed";

export interface PipelineStep {
  step: string;
  status: NodeStatus;
  input_summary?: string | null;
  output_summary?: string | null;
}

export interface PatchCandidate {
  candidate_id: string;
  source: string;
  patch_text: string;
  syntax_valid: boolean;
  applies_cleanly: boolean;
  tests_passed: string[];
  tests_failed: string[];
  rank_score: number | null;
  is_selected: boolean;
}

export interface RunResult {
  instance_id: string;
  status: string;
  plan: Record<string, unknown> | null;
  retrieved_chunks: Record<string, unknown>[];
  candidates: PatchCandidate[];
  final_patch: string | null;
  resolved: boolean | null;
  explanation: string | null;
  pipeline_steps: PipelineStep[];
}

export interface IssueSubmission {
  repo: string;
  issueUrl?: string;
  issueText?: string;
  baseCommit: string;
}

export type RunOutcome = "running" | "resolved" | "unresolved" | "error";

export interface RunRecord {
  id: string;
  repo: string;
  baseCommit: string;
  issuePreview: string;
  submittedAt: number;
  completedAt?: number;
  outcome: RunOutcome;
  errorMessage?: string;
  result: RunResult | null;
}
