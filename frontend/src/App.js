import React from "react";
import "./App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { BrandingProvider } from "./context/BrandingContext";
import ProtectedRoute from "./components/ProtectedRoute";
import Layout from "./components/Layout";
import { Toaster } from "sonner";

import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Clienti from "./pages/Clienti";
import Articoli from "./pages/Articoli";
import Listini from "./pages/Listini";
import DDT from "./pages/DDT";
import Sospesi from "./pages/Sospesi";
import Fatture from "./pages/Fatture";
import Utenti from "./pages/Utenti";
import Pricing from "./pages/Pricing";
import Register from "./pages/Register";
import Billing from "./pages/Billing";
import SuperAdmin from "./pages/SuperAdmin";
import Branding from "./pages/Branding";
import Azienda from "./pages/Azienda";
import VerifyEmail from "./pages/VerifyEmail";

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
        <BrandingProvider>
          <Toaster position="top-right" richColors closeButton />
          <BrowserRouter>
            <Routes>
              <Route path="/" element={<RootRedirect />} />
              <Route path="/login" element={<Login />} />
              <Route path="/pricing" element={<Pricing />} />
              <Route path="/register" element={<Register />} />
              <Route path="/verify" element={<VerifyEmail />} />
              <Route path="/billing" element={<WithLayout roles={["admin"]}><Billing /></WithLayout>} />
              <Route path="/admin" element={<WithLayout roles={["superadmin"]}><SuperAdmin /></WithLayout>} />
              <Route path="/admin/branding" element={<WithLayout roles={["superadmin"]}><Branding /></WithLayout>} />
              <Route path="/dashboard" element={<WithLayout><Dashboard /></WithLayout>} />
              <Route path="/clienti" element={<WithLayout roles={["admin","contabilita","logistica"]}><Clienti /></WithLayout>} />
              <Route path="/articoli" element={<WithLayout roles={["admin","contabilita"]}><Articoli /></WithLayout>} />
              <Route path="/listini" element={<WithLayout roles={["admin","contabilita"]}><Listini /></WithLayout>} />
              <Route path="/ddt" element={<WithLayout roles={["admin","logistica","contabilita"]}><DDT /></WithLayout>} />
              <Route path="/fatture" element={<WithLayout roles={["admin","contabilita"]}><Fatture /></WithLayout>} />
              <Route path="/sospesi" element={<WithLayout roles={["admin","contabilita"]}><Sospesi /></WithLayout>} />
              <Route path="/utenti" element={<WithLayout roles={["admin"]}><Utenti /></WithLayout>} />
              <Route path="/azienda" element={<WithLayout roles={["admin"]}><Azienda /></WithLayout>} />
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </BrowserRouter>
        </BrandingProvider>
      </AuthProvider>
    </div>
  );
}
