import React, { useEffect, useRef, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import TrialBanner from "./TrialBanner";
import {
  ChartBar, Users, Package, HardDrives, ClipboardText, Path, Kanban,
  ShieldCheck, Truck, Receipt, UserList, Hand, DeviceMobile, Storefront,
  SignOut, List, X, Sparkle, Drop, Wrench, ChatCircleText, Scan, CreditCard, ChartLineUp, Crown, CurrencyEur,
} from "@phosphor-icons/react";

const ALL_ITEMS = [
  { to: "/dashboard", label: "Dashboard", icon: ChartBar, roles: ["admin", "produzione", "logistica", "qualita", "contabilita"] },
  { to: "/clienti", label: "Clienti", icon: Users, roles: ["admin", "contabilita", "logistica"] },
  { to: "/articoli", label: "Articoli", icon: Package, roles: ["admin", "contabilita", "produzione"] },
  { to: "/listini", label: "Listini", icon: Receipt, roles: ["admin", "contabilita"] },
  { to: "/macchine", label: "Macchine", icon: HardDrives, roles: ["admin", "produzione"] },
  { to: "/ddt", label: "D.D.T.", icon: Truck, roles: ["admin", "logistica", "contabilita"] },
  { to: "/fatture", label: "Fatturazione", icon: Receipt, roles: ["admin", "contabilita"] },
  { to: "/sospesi", label: "Sospesi", icon: CurrencyEur, roles: ["admin", "contabilita"] },
  { to: "/magazzino", label: "Magazzino", icon: Drop, roles: ["admin", "produzione", "contabilita", "logistica"] },
  { to: "/manutenzione", label: "Manutenzione", icon: Wrench, roles: ["admin", "produzione"] },
  { to: "/notifiche", label: "Notifiche", icon: ChatCircleText, roles: ["admin", "logistica", "produzione", "qualita"] },
  { to: "/hardware", label: "Console Hardware", icon: Scan, roles: ["admin", "produzione", "logistica"] },
  { to: "/utenti", label: "Utenti & Audit", icon: UserList, roles: ["admin"] },
  { to: "/insights", label: "Insights & Forecast", icon: ChartLineUp, roles: ["admin", "produzione", "contabilita"] },
  { to: "/billing", label: "Abbonamento", icon: CreditCard, roles: ["admin"] },
  { to: "/admin", label: "Pannello SaaS", icon: Crown, roles: ["superadmin"] },
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
  const touchStart = useRef(null);

  // Swipe-from-left gesture to open sidebar (iPad/mobile only, xl viewports use sticky sidebar)
  useEffect(() => {
    const XL_BP = 1280;
    const EDGE = 24; // px from left edge to start swipe
    const THRESHOLD_OPEN = 60; // min horizontal distance to trigger open
    const THRESHOLD_CLOSE = 60; // min horizontal distance to trigger close
    const MAX_VERTICAL = 80; // abort if user scrolls vertically instead

    const onStart = (e) => {
      if (window.innerWidth >= XL_BP) return;
      const t = e.touches[0];
      // Open gesture: only when closed + started from left edge
      if (!mobileOpen && t.clientX <= EDGE) {
        touchStart.current = { x: t.clientX, y: t.clientY, mode: "open" };
        return;
      }
      // Close gesture: only when open + started inside sidebar area
      if (mobileOpen && t.clientX <= 256) {
        touchStart.current = { x: t.clientX, y: t.clientY, mode: "close" };
      }
    };

    const onEnd = (e) => {
      const s = touchStart.current;
      if (!s) return;
      touchStart.current = null;
      const t = (e.changedTouches && e.changedTouches[0]) || null;
      if (!t) return;
      const dx = t.clientX - s.x;
      const dy = Math.abs(t.clientY - s.y);
      if (dy > MAX_VERTICAL) return;
      if (s.mode === "open" && dx > THRESHOLD_OPEN) setMobileOpen(true);
      if (s.mode === "close" && dx < -THRESHOLD_CLOSE) setMobileOpen(false);
    };

    document.addEventListener("touchstart", onStart, { passive: true });
    document.addEventListener("touchend", onEnd, { passive: true });
    return () => {
      document.removeEventListener("touchstart", onStart);
      document.removeEventListener("touchend", onEnd);
    };
  }, [mobileOpen]);

  const items = ALL_ITEMS.filter(i => {
    if (!i.roles) return true;
    if (user.role === "superadmin") return i.roles.includes("superadmin") || true;
    return i.roles.includes(user.role) || user.role === "admin";
  });

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen flex bg-slate-50">
      {/* Sidebar */}
      <aside className={`fixed xl:sticky top-0 left-0 z-40 w-64 h-screen bg-slate-900 text-white flex flex-col border-r border-slate-800 transform transition-transform ${mobileOpen ? "translate-x-0" : "-translate-x-full xl:translate-x-0"}`}>
        <div className="h-16 flex items-center gap-2 px-5 border-b border-slate-800">
          <div className="w-8 h-8 rounded-md bg-gradient-to-br from-azzurro to-indaco flex items-center justify-center">
            <Sparkle size={18} weight="fill" className="text-white" />
          </div>
          <div>
            <div className="font-display font-bold text-lg leading-none tracking-tight">CleanTec</div>
            <div className="text-[10px] text-slate-400 font-mono uppercase tracking-widest mt-0.5">ERP • MES • WMS</div>
          </div>
          <button className="ml-auto xl:hidden text-slate-400 hover:text-white" onClick={() => setMobileOpen(false)} data-testid="close-menu-btn">
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
        <TrialBanner />
        <header className="h-16 xl:hidden bg-white border-b border-slate-200 flex items-center px-4 sticky top-0 z-30">
          <button onClick={() => setMobileOpen(true)} className="text-slate-600" data-testid="open-menu-btn">
            <List size={24} />
          </button>
          <div className="ml-4 font-display font-bold text-lg">CleanTec</div>
        </header>

        <main className="flex-1 p-4 sm:p-6 lg:p-8 animate-fade-in">
          {children}
        </main>
      </div>

      {mobileOpen && <div className="fixed inset-0 bg-black/40 z-30 xl:hidden" onClick={() => setMobileOpen(false)}></div>}

      {/* Swipe hint: subtle edge indicator on iPad/mobile when sidebar is closed */}
      {!mobileOpen && (
        <div
          className="fixed left-0 top-1/2 -translate-y-1/2 w-1 h-16 bg-indaco/30 rounded-r-full xl:hidden pointer-events-none animate-pulse"
          aria-hidden="true"
          data-testid="swipe-hint"
        />
      )}
    </div>
  );
}
