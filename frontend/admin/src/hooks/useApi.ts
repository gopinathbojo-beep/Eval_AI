import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";

export function useApi<T>(path: string | null, pollMs?: (data: T) => number | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(!!path);
  const timer = useRef<number | undefined>(undefined);
  const poll = useRef(pollMs);
  poll.current = pollMs;

  const load = useCallback(async () => {
    if (!path) return;
    try {
      const d = await api<T>(path);
      setData(d); setError(null);
      const ms = poll.current?.(d);
      if (ms) timer.current = window.setTimeout(load, ms);
    } catch (e) {
      setError(e as ApiError);
    } finally { setLoading(false); }
  }, [path]);

  useEffect(() => { setLoading(!!path); load(); return () => window.clearTimeout(timer.current); }, [load, path]);
  const reload = useCallback(() => { window.clearTimeout(timer.current); return load(); }, [load]);
  return { data, error, loading, reload, setData };
}
