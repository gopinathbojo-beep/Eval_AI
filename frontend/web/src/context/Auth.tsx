import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, setUnauthorizedHandler } from "../api/client";
import { PORTAL } from "../config/config";
import type { Session, User } from "../types";

interface AuthCtx {
  /** Whoever is signed in: school management, a teacher, a parent, or a console account. */
  user: User | null;
  /** The same account; the exam pages read it under this name. */
  teacher: User | null;
  loading: boolean;
  login(email: string, password: string): Promise<User>;
  loginGoogle(idToken: string): Promise<User>;
  /** Show a session the server started (signup, invite, password change); its cookie is already set. */
  adopt(s: Session): void;
  refresh(): Promise<void>;
  logout(): void;
}
const Ctx = createContext<AuthCtx>(null!);
export const useAuth = () => useContext(Ctx);

/** The session lives in an HttpOnly cookie the server sets; JavaScript never holds a token. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const adopt = useCallback((s: Session) => setUser(s.user ?? s.teacher ?? null), []);
  const logout = useCallback(() => {
    void api("/auth/logout", { method: "POST" }).then(() => {
      window.location.replace("/login");
    }).catch(() => window.alert("Could not sign out. Check your connection and try again."));
  }, []);
  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
    try { localStorage.removeItem("adem_token"); } catch { /* remove legacy browser tokens */ }
    const controller = new AbortController();
    api<User>("/auth/me", { signal: controller.signal }).then(setUser).catch(() => {}).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => { controller.abort(); setUnauthorizedHandler(() => {}); };
  }, []);
  const login = async (email: string, password: string) => {
    const s = await api<Session>("/auth/login", { method: "POST", json: { email, password, portal: PORTAL, browser_session: true } });
    adopt(s);
    return s.user;
  };
  const loginGoogle = async (idToken: string) => {
    const s = await api<Session>("/auth/google", { method: "POST", json: { id_token: idToken, portal: PORTAL, browser_session: true } });
    adopt(s);
    return s.user;
  };
  const refresh = useCallback(async () => { setUser(await api<User>("/auth/me")); }, []);
  return <Ctx.Provider value={{ user, teacher: user, loading, login, loginGoogle, adopt, refresh, logout }}>{children}</Ctx.Provider>;
}
