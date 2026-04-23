import React from "react";
import "./App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import Layout from "./components/Layout";
import { Toaster } from "sonner";

import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Clienti from "./pages/Clienti";
import Articoli from "./pages/Articoli";
import Macchine from "./pages/Macchine";
import Accettazione from "./pages/Accettazione";
import Lotti from "./pages/Lotti";
import Produzione from "./pages/Produzione";
import Qualita from "./pages/Qualita";
import Logistica from "./pages/Logistica";
import Fatture from "./pages/Fatture";
import Utenti from "./pages/Utenti";
import Touch from "./pages/Touch";
import Mobile from "./pages/Mobile";
import Portale from "./pages/Portale";

function WithLayout({ children, roles }) {
  return (
    <ProtectedRoute roles={roles}>
      <Layout>{children}</Layout>
    </ProtectedRoute>
  );
}

function RootRedirect() {
  const { user } = useAuth();
  if (user === null) return null;
  if (user === false) return <Navigate to="/login" replace />;
  return <Navigate to="/dashboard" replace />;
}

export default function App() {
  return (
    <div className="App">
      <AuthProvider>
        <Toaster position="top-right" richColors closeButton />
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<RootRedirect />} />
            <Route path="/login" element={<Login />} />
            <Route path="/dashboard" element={<WithLayout><Dashboard /></WithLayout>} />
            <Route path="/clienti" element={<WithLayout><Clienti /></WithLayout>} />
            <Route path="/articoli" element={<WithLayout><Articoli /></WithLayout>} />
            <Route path="/macchine" element={<WithLayout><Macchine /></WithLayout>} />
            <Route path="/accettazione" element={<WithLayout><Accettazione /></WithLayout>} />
            <Route path="/lotti" element={<WithLayout><Lotti /></WithLayout>} />
            <Route path="/produzione" element={<WithLayout><Produzione /></WithLayout>} />
            <Route path="/qualita" element={<WithLayout><Qualita /></WithLayout>} />
            <Route path="/logistica" element={<WithLayout><Logistica /></WithLayout>} />
            <Route path="/fatture" element={<WithLayout><Fatture /></WithLayout>} />
            <Route path="/utenti" element={<WithLayout roles={["admin"]}><Utenti /></WithLayout>} />
            <Route path="/touch" element={<ProtectedRoute><Touch /></ProtectedRoute>} />
            <Route path="/mobile" element={<ProtectedRoute><Mobile /></ProtectedRoute>} />
            <Route path="/portale" element={<ProtectedRoute><Portale /></ProtectedRoute>} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </div>
  );
}
