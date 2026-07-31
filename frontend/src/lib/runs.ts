import { useCallback, useEffect, useState } from "react";
import { RunRecord } from "./types";

const STORAGE_KEY = "swe-agent-runs";
const MAX_HISTORY = 20;

function load(): RunRecord[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function save(runs: RunRecord[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(runs.slice(0, MAX_HISTORY)));
  } catch {
    // localStorage unavailable (private browsing, quota) -- history is
    // best-effort, session state in React still works without persistence.
  }
}

function makeId(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `run-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function useRunHistory() {
  const [runs, setRuns] = useState<RunRecord[]>(() => load());

  useEffect(() => {
    save(runs);
  }, [runs]);

  const startRun = useCallback((repo: string, baseCommit: string, issuePreview: string): string => {
    const id = makeId();
    const record: RunRecord = {
      id,
      repo,
      baseCommit,
      issuePreview,
      submittedAt: Date.now(),
      outcome: "running",
      result: null,
    };
    setRuns((prev) => [record, ...prev].slice(0, MAX_HISTORY));
    return id;
  }, []);

  const completeRun = useCallback((id: string, patch: Partial<RunRecord>) => {
    setRuns((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  }, []);

  const removeRun = useCallback((id: string) => {
    setRuns((prev) => prev.filter((r) => r.id !== id));
  }, []);

  return { runs, startRun, completeRun, removeRun };
}
