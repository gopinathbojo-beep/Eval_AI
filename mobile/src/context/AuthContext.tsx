import React, { createContext, useContext, useEffect, useState } from "react";
import { api, getToken, setToken, setUnauthorizedHandler } from "../api/client";
import type { Teacher } from "../types";

interface AuthContextType {
  teacher: Teacher | null;
  isAuthenticated: boolean;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  reloadProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  teacher: null,
  isAuthenticated: false,
  loading: true,
  login: async () => {},
  logout: async () => {},
  reloadProfile: async () => {},
});

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [teacher, setTeacher] = useState<Teacher | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchProfile = async () => {
    try {
      const token = await getToken();
      if (!token) {
        setTeacher(null);
        return;
      }
      const data = await api<Teacher>("/auth/me");
      setTeacher(data);
    } catch {
      setTeacher(null);
      await setToken(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setTeacher(null);
    });
    fetchProfile();
  }, []);

  const login = async (email: string, password: string) => {
    const res = await api<{ access_token: string }>("/auth/login", {
      method: "POST",
      json: { email: email.trim().toLowerCase(), password },
    });
    await setToken(res.access_token);
    await fetchProfile();
  };

  const logout = async () => {
    await setToken(null);
    setTeacher(null);
  };

  return (
    <AuthContext.Provider
      value={{
        teacher,
        isAuthenticated: !!teacher,
        loading,
        login,
        logout,
        reloadProfile: fetchProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
