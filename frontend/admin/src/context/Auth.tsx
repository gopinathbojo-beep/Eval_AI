import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, getToken, setToken, setUnauthorizedHandler } from "../api/client";
import { PORTAL } from "../config/config";
import type { Session, User } from "../types";

interface AuthCtx {
  user: User | null;
  loading: boolean;
  login(email: string, password: string): Promise<void>;
  loginGoogle(idToken: string): Promise<void>;
  /** Store a session the server handed back (signup, invite, password change). */
  adopt(s: Session): void;
  logout(): void;
  logoutEverywhere(): Promise<void>;
}
const Ctx = createContext<AuthCtx>(null!);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(!!getToken());
  const adopt = useCallback((s: Session) => { setToken(s.access_token); setUser(s.user); }, []);
  const logout = useCallback(() => {
    if (getToken()) api("/auth/logout", { method: "POST" }).catch(() => {});
    setToken(null);
    setUser(null);
  }, []);
  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
    if (getToken()) api<User>("/auth/me").then(setUser).catch(() => setToken(null)).finally(() => setLoading(false));
  }, []);
  const login = async (email: string, password: string) =>
    adopt(await api<Session>("/auth/login", { method: "POST", json: { email, password, portal: PORTAL } }));
  const loginGoogle = async (idToken: string) =>
    adopt(await api<Session>("/auth/google", { method: "POST", json: { id_token: idToken, portal: PORTAL } }));
  const logoutEverywhere = async () => {
    await api("/auth/logout-all", { method: "POST" });
    setToken(null);
    setUser(null);
  };
  return <Ctx.Provider value={{ user, loading, login, loginGoogle, adopt, logout, logoutEverywhere }}>{children}</Ctx.Provider>;
}
