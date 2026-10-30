import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";

export function useApi<T>(path: string | null, pollMs?: (data: T) => number | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(!!path);
  const poll = useRef(pollMs);
  poll.current = pollMs;
  const loadRef = useRef<() => Promise<void>>(async () => {});

  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    let controller: AbortController | undefined;
    const load = async () => {
      window.clearTimeout(timer);
      controller?.abort();
      if (!path || !active) return;
      const current = new AbortController();
      controller = current;
      try {
        const d = await api<T>(path, { signal: current.signal });
        if (!active || current.signal.aborted) return;
        setData(d); setError(null);
        const ms = poll.current?.(d);
        if (ms) timer = window.setTimeout(load, ms);
      } catch (e) {
        if (!active || current.signal.aborted) return;
        setError(e as ApiError);
        if (poll.current && (e as ApiError).status !== 401) timer = window.setTimeout(load, 10_000);
      } finally {
        if (active && !current.signal.aborted) setLoading(false);
      }
    };
    loadRef.current = load;
    setData(null); setError(null); setLoading(!!path);
    void load();
    return () => { active = false; controller?.abort(); window.clearTimeout(timer); };
  }, [path]);
  const reload = useCallback(() => loadRef.current(), []);
  return { data, error, loading, reload, setData };
}
