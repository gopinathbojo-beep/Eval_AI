import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, setUnauthorizedHandler } from "../api/client";
import type { Teacher } from "../types";

interface AuthCtx { teacher: Teacher | null; loading: boolean; login(e: string, p: string): Promise<Teacher>; refresh(): Promise<void>; logout(): void }
const Ctx = createContext<AuthCtx>(null!);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [teacher, setTeacher] = useState<Teacher | null>(null);
  const [loading, setLoading] = useState(true);
  const logout = useCallback(() => {
    void api("/auth/logout", { method: "POST" }).then(() => {
      window.location.replace("/login");
    }).catch(() => window.alert("Could not sign out. Check your connection and try again."));
  }, []);
  useEffect(() => {
    setUnauthorizedHandler(() => setTeacher(null));
    try { localStorage.removeItem("adem_token"); } catch { /* remove legacy browser tokens */ }
    const controller = new AbortController();
    api<Teacher>("/auth/me", { signal: controller.signal }).then(setTeacher).catch(() => {}).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => { controller.abort(); setUnauthorizedHandler(() => {}); };
  }, []);
  const login = async (email: string, password: string) => {
    const r = await api<{ teacher: Teacher }>("/auth/login", { method: "POST", json: { email, password, browser_session: true } });
    setTeacher(r.teacher);
    return r.teacher;
  };
  const refresh = useCallback(async () => { setTeacher(await api<Teacher>("/auth/me")); }, []);
  return <Ctx.Provider value={{ teacher, loading, login, refresh, logout }}>{children}</Ctx.Provider>;
}
