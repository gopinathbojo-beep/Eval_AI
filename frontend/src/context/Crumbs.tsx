import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

/**
 * Human names for ID segments in the URL, so breadcrumbs read "Physics Mid-Term" rather than "Details".
 * Pages that load a record register its name with useCrumbName(id, name); AppLayout reads them back.
 */
interface CrumbCtx {
  names: Record<string, string>;
  setName: (id: string, name: string | null) => void;
}
const Ctx = createContext<CrumbCtx>({ names: {}, setName: () => {} });

export function CrumbProvider({ children }: { children: ReactNode }) {
  const [names, setNames] = useState<Record<string, string>>({});
  const setName = useCallback((id: string, name: string | null) => {
    setNames((prev) => {
      if (!name) {
        if (!(id in prev)) return prev;
        const { [id]: _, ...rest } = prev;
        return rest;
      }
      return prev[id] === name ? prev : { ...prev, [id]: name };
    });
  }, []);
  return <Ctx.Provider value={{ names, setName }}>{children}</Ctx.Provider>;
}

export const useCrumbNames = () => useContext(Ctx).names;

/** Label the URL segment `id` with `name` while the calling page is mounted. */
export function useCrumbName(id: string | undefined, name: string | null | undefined) {
  const { setName } = useContext(Ctx);
  useEffect(() => {
    if (!id || !name) return;
    setName(id, name);
    return () => setName(id, null);
  }, [id, name, setName]);
}
