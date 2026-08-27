import React from "react";
import "./App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { BrandingProvider } from "./context/BrandingContext";
import ProtectedRoute from "./components/ProtectedRoute";
import Layout from "./components/Layout";
import { VersionProvider } from "./components/VersionWatcher";
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
import SuperadminUsers from "./pages/SuperadminUsers";
import Branding from "./pages/Branding";
import Azienda from "./pages/Azienda";
import BackupDati from "./pages/BackupDati";
import Offerte from "./pages/Offerte";
import Ordinativi from "./pages/Ordinativi";
import PortalePublic from "./pages/PortalePublic";
import PortaleAccesso from "./pages/PortaleAccesso";
import Fornitori from "./pages/Fornitori";
import DdtFornitore from "./pages/DdtFornitore";
import FattureFornitore from "./pages/FattureFornitore";
import Costi from "./pages/Costi";
import Report from "./pages/Report";
import Dipendenti from "./pages/Dipendenti";
import Automezzi from "./pages/Automezzi";
import VerifyEmail from "./pages/VerifyEmail";
import Produzione from "./pages/Produzione";
import Consegne from "./pages/Consegne";

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
  if (user.role === "produzione") return <Navigate to="/produzione" replace />;
  return <Navigate to="/dashboard" replace />;
}

export default function App() {
  return (
    <div className="App">
      <AuthProvider>
        <BrandingProvider>
          <VersionProvider>
            <Toaster position="top-right" richColors closeButton />
            <BrowserRouter>
            <Routes>
              <Route path="/" element={<RootRedirect />} />
              <Route path="/login" element={<Login />} />
              <Route path="/pricing" element={<Pricing />} />
              <Route path="/register" element={<Register />} />
              <Route path="/verify" element={<VerifyEmail />} />
            <Route path="/ordina/:token" element={<PortalePublic />} />
            <Route path="/portale" element={<PortaleAccesso />} />
            <Route path="/produzione" element={<Produzione />} />
              <Route path="/billing" element={<WithLayout roles={["admin"]}><Billing /></WithLayout>} />
              <Route path="/admin" element={<WithLayout roles={["superadmin"]}><SuperAdmin /></WithLayout>} />
              <Route path="/admin/superadmins" element={<WithLayout roles={["superadmin"]}><SuperadminUsers /></WithLayout>} />
              <Route path="/admin/branding" element={<WithLayout roles={["superadmin"]}><Branding /></WithLayout>} />
              <Route path="/dashboard" element={<WithLayout><Dashboard /></WithLayout>} />
              <Route path="/clienti" element={<WithLayout roles={["admin","contabilita","logistica"]}><Clienti /></WithLayout>} />
              <Route path="/articoli" element={<WithLayout roles={["admin","contabilita"]}><Articoli /></WithLayout>} />
              <Route path="/listini" element={<WithLayout roles={["admin","contabilita"]}><Listini /></WithLayout>} />
              <Route path="/ddt" element={<WithLayout roles={["admin","logistica","contabilita"]}><DDT /></WithLayout>} />
              <Route path="/fatture" element={<WithLayout roles={["admin","contabilita"]}><Fatture /></WithLayout>} />
              <Route path="/sospesi" element={<WithLayout roles={["admin","contabilita"]}><Sospesi /></WithLayout>} />
              <Route path="/offerte" element={<WithLayout roles={["admin","contabilita"]}><Offerte /></WithLayout>} />
              <Route path="/ordinativi" element={<WithLayout roles={["admin","logistica","contabilita"]}><Ordinativi /></WithLayout>} />
              <Route path="/consegne" element={<WithLayout roles={["admin","logistica","contabilita"]}><Consegne /></WithLayout>} />
              <Route path="/fornitori" element={<WithLayout roles={["admin","contabilita"]}><Fornitori /></WithLayout>} />
              <Route path="/fornitori/ddt" element={<WithLayout roles={["admin","logistica","contabilita"]}><DdtFornitore /></WithLayout>} />
              <Route path="/fornitori/fatture" element={<WithLayout roles={["admin","contabilita"]}><FattureFornitore /></WithLayout>} />
              <Route path="/costi" element={<WithLayout roles={["admin","contabilita"]}><Costi /></WithLayout>} />
              <Route path="/report" element={<WithLayout roles={["admin","contabilita"]}><Report /></WithLayout>} />
              <Route path="/dipendenti" element={<WithLayout roles={["admin","contabilita"]}><Dipendenti /></WithLayout>} />
              <Route path="/automezzi" element={<WithLayout roles={["admin","contabilita"]}><Automezzi /></WithLayout>} />
              <Route path="/utenti" element={<WithLayout roles={["admin"]}><Utenti /></WithLayout>} />
              <Route path="/azienda" element={<WithLayout roles={["admin"]}><Azienda /></WithLayout>} />
              <Route path="/backup-dati" element={<WithLayout roles={["admin"]}><BackupDati /></WithLayout>} />
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </BrowserRouter>
          </VersionProvider>
        </BrandingProvider>
      </AuthProvider>
    </div>
  );
}
