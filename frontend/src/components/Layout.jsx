import React, { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import {
  ChartBar, Users, Package, HardDrives, ClipboardText, Path, Kanban,
  ShieldCheck, Truck, Receipt, UserList, Hand, DeviceMobile, Storefront,
  SignOut, List, X, Sparkle, Drop,
} from "@phosphor-icons/react";

const ALL_ITEMS = [
  { to: "/dashboard", label: "Dashboard", icon: ChartBar, roles: ["admin", "produzione", "logistica", "qualita", "contabilita"] },
  { to: "/clienti", label: "Clienti", icon: Users, roles: ["admin", "contabilita", "logistica"] },
  { to: "/articoli", label: "Articoli", icon: Package, roles: ["admin", "contabilita", "produzione"] },
  { to: "/macchine", label: "Macchine", icon: HardDrives, roles: ["admin", "produzione"] },
  { to: "/accettazione", label: "Accettazione", icon: ClipboardText, roles: ["admin", "logistica", "produzione"] },
  { to: "/lotti", label: "Tracciabilità Lotti", icon: Path, roles: ["admin", "produzione", "qualita", "logistica"] },
  { to: "/produzione", label: "Produzione MES", icon: Kanban, roles: ["admin", "produzione"] },
  { to: "/qualita", label: "Controllo Qualità", icon: ShieldCheck, roles: ["admin", "qualita", "produzione"] },
  { to: "/logistica", label: "Logistica", icon: Truck, roles: ["admin", "logistica"] },
  { to: "/fatture", label: "Fatturazione", icon: Receipt, roles: ["admin", "contabilita"] },
  { to: "/magazzino", label: "Magazzino", icon: Drop, roles: ["admin", "produzione", "contabilita", "logistica"] },
  { to: "/utenti", label: "Utenti & Audit", icon: UserList, roles: ["admin"] },
];

const SPECIAL_ITEMS = [
  { to: "/touch", label: "Modalità Touch", icon: Hand },
  { to: "/mobile", label: "App Autista", icon: DeviceMobile },
  { to: "/portale", label: "Portale Cliente", icon: Storefront },
];

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);

  const items = ALL_ITEMS.filter(i => !i.roles || i.roles.includes(user.role) || user.role === "admin");

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen flex bg-slate-50">
      {/* Sidebar */}
      <aside className={`fixed lg:sticky top-0 left-0 z-40 w-64 h-screen bg-slate-900 text-white flex flex-col border-r border-slate-800 transform transition-transform ${mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`}>
        <div className="h-16 flex items-center gap-2 px-5 border-b border-slate-800">
          <div className="w-8 h-8 rounded-md bg-gradient-to-br from-azzurro to-indaco flex items-center justify-center">
            <Sparkle size={18} weight="fill" className="text-white" />
          </div>
          <div>
            <div className="font-display font-bold text-lg leading-none tracking-tight">CleanTec</div>
            <div className="text-[10px] text-slate-400 font-mono uppercase tracking-widest mt-0.5">ERP • MES • WMS</div>
          </div>
          <button className="ml-auto lg:hidden text-slate-400 hover:text-white" onClick={() => setMobileOpen(false)} data-testid="close-menu-btn">
            <X size={20} />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-0.5">
          <div className="overline px-3 mb-2 text-slate-500">Operativo</div>
          {items.map((it) => (
            <NavLink
              key={it.to}
              to={it.to}
              data-testid={`nav-${it.to.replace("/", "")}`}
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) =>
                `sidebar-item ${isActive ? "sidebar-item-active" : "text-slate-300"}`
              }
            >
              <it.icon size={18} weight="regular" />
              <span>{it.label}</span>
            </NavLink>
          ))}

          <div className="overline px-3 mt-6 mb-2 text-slate-500">Interfacce</div>
          {SPECIAL_ITEMS.map((it) => (
            <NavLink
              key={it.to}
              to={it.to}
              data-testid={`nav-${it.to.replace("/", "")}`}
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) =>
                `sidebar-item ${isActive ? "sidebar-item-active" : "text-slate-300"}`
              }
            >
              <it.icon size={18} weight="regular" />
              <span>{it.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-slate-800 p-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-celeste to-indaco flex items-center justify-center text-sm font-bold">
              {user.name?.[0]?.toUpperCase() || "?"}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium truncate" data-testid="sidebar-user-name">{user.name}</div>
              <div className="text-[10px] text-slate-400 uppercase tracking-widest font-mono">{user.role}</div>
            </div>
            <button onClick={handleLogout} className="text-slate-400 hover:text-white" data-testid="logout-btn" title="Esci">
              <SignOut size={18} />
            </button>
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 min-w-0 flex flex-col">
        <header className="h-16 lg:hidden bg-white border-b border-slate-200 flex items-center px-4 sticky top-0 z-30">
          <button onClick={() => setMobileOpen(true)} className="text-slate-600" data-testid="open-menu-btn">
            <List size={24} />
          </button>
          <div className="ml-4 font-display font-bold text-lg">CleanTec</div>
        </header>

        <main className="flex-1 p-4 sm:p-6 lg:p-8 animate-fade-in">
          {children}
        </main>
      </div>

      {mobileOpen && <div className="fixed inset-0 bg-black/40 z-30 lg:hidden" onClick={() => setMobileOpen(false)}></div>}
    </div>
  );
}
