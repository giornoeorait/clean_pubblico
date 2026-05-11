import React, { createContext, useContext, useEffect, useState } from "react";
import api, { formatApiErrorDetail } from "../lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null=loading, false=unauth, object=auth
  const [error, setError] = useState("");

  useEffect(() => {
    // Skip auth ping on public routes (e.g. /ordina/:token, /portale) to avoid spurious 401 in console
    if (typeof window !== "undefined" && (window.location.pathname.startsWith("/ordina/") || window.location.pathname === "/portale")) {
      setUser(false);
      return;
    }
    (async () => {
      try {
        const { data } = await api.get("/auth/me");
        setUser(data);
      } catch (e) {
        setUser(false);
      }
    })();
  }, []);

  const login = async (email, password) => {
    setError("");
    try {
      const { data } = await api.post("/auth/login", { email, password });
      if (data.token) localStorage.setItem("cleantec_token", data.token);
      setUser(data.user);
      return true;
    } catch (e) {
      setError(formatApiErrorDetail(e.response?.data?.detail) || e.message);
      return false;
    }
  };

  const logout = async () => {
    try {
      await api.post("/auth/logout");
    } catch {}
    localStorage.removeItem("cleantec_token");
    setUser(false);
  };

  return (
    <AuthContext.Provider value={{ user, setUser, login, logout, error }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
