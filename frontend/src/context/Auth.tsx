import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, getToken, setToken, setUnauthorizedHandler } from "../api/client";
import type { Teacher } from "../types";

interface AuthCtx { teacher: Teacher | null; loading: boolean; login(e: string, p: string): Promise<void>; logout(): void }
const Ctx = createContext<AuthCtx>(null!);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [teacher, setTeacher] = useState<Teacher | null>(null);
  const [loading, setLoading] = useState(!!getToken());
  const logout = useCallback(() => { setToken(null); setTeacher(null); }, []);
  useEffect(() => {
    setUnauthorizedHandler(() => setTeacher(null));
    if (getToken()) api<Teacher>("/auth/me").then(setTeacher).catch(() => setToken(null)).finally(() => setLoading(false));
  }, []);
  const login = async (email: string, password: string) => {
    const r = await api<{ access_token: string; teacher: Teacher }>("/auth/login", { method: "POST", json: { email, password } });
    setToken(r.access_token);
    setTeacher(r.teacher);
  };
  return <Ctx.Provider value={{ teacher, loading, login, logout }}>{children}</Ctx.Provider>;
}
