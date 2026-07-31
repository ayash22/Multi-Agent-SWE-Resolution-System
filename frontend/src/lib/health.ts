import { useEffect, useState } from "react";

export type HealthState = "checking" | "ok" | "down";

const POLL_INTERVAL_MS = 20_000;

export function useBackendHealth(apiBaseUrl: string): HealthState {
  const [state, setState] = useState<HealthState>("checking");

  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      try {
        const res = await fetch(`${apiBaseUrl}/health`, { signal: AbortSignal.timeout(5000) });
        if (!cancelled) setState(res.ok ? "ok" : "down");
      } catch {
        if (!cancelled) setState("down");
      }
    };

    check();
    const interval = setInterval(check, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [apiBaseUrl]);

  return state;
}
