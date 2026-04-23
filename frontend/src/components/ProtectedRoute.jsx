import React from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({ children, roles }) {
  const { user } = useAuth();
  if (user === null) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="flex items-center gap-3 text-slate-500" data-testid="loading-auth">
          <span className="inline-block w-2 h-2 bg-azzurro rounded-full animate-pulse-dot"></span>
          <span className="font-mono text-sm">Verifica sessione…</span>
        </div>
      </div>
    );
  }
  if (user === false) return <Navigate to="/login" replace />;
  if (roles && roles.length && !roles.includes(user.role) && user.role !== "admin") {
    return <Navigate to="/dashboard" replace />;
  }
  return children;
}
