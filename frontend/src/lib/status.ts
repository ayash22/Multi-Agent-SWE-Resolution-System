import { CheckCircle2, CircleDashed, Loader2, XCircle } from "lucide-react";
import { Tone } from "../components/ui/Badge";
import { NodeStatus, RunOutcome } from "./types";

export function nodeStatusVisual(status: NodeStatus): {
  tone: Tone;
  label: string;
  icon: typeof CheckCircle2;
  pulse: boolean;
} {
  switch (status) {
    case "done":
      return { tone: "success", label: "Done", icon: CheckCircle2, pulse: false };
    case "running":
      return { tone: "warning", label: "Running", icon: Loader2, pulse: true };
    case "failed":
      return { tone: "danger", label: "Failed", icon: XCircle, pulse: false };
    default:
      return { tone: "neutral", label: "Pending", icon: CircleDashed, pulse: false };
  }
}

export function runOutcomeVisual(outcome: RunOutcome): {
  tone: Tone;
  label: string;
  icon: typeof CheckCircle2;
  pulse: boolean;
} {
  switch (outcome) {
    case "resolved":
      return { tone: "success", label: "Resolved", icon: CheckCircle2, pulse: false };
    case "unresolved":
      return { tone: "warning", label: "Unresolved", icon: XCircle, pulse: false };
    case "error":
      return { tone: "danger", label: "Error", icon: XCircle, pulse: false };
    default:
      return { tone: "info", label: "Running", icon: Loader2, pulse: true };
  }
}
