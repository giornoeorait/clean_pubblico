import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import axios from "axios";

const BACKEND = process.env.REACT_APP_BACKEND_URL;
const BrandingContext = createContext(null);

const DEFAULTS = {
  app_name: "CleanTec",
  tagline: "Industrial Laundry OS",
  login_eyebrow: "Control Room",
  login_title: "Il sistema nervoso della tua lavanderia industriale.",
  login_subtitle: "ERP commerciale completo: clienti, listini multipli, D.D.T. automatici e fatturazione aggregata in un unico ambiente.",
  login_features: [
    { icon: "truck", label: "D.D.T. automatici" },
    { icon: "factory", label: "Listini multipli" },
    { icon: "shield", label: "Gestione sospesi" },
    { icon: "chart", label: "KPI Real-time" },
  ],
  login_footer: "© 2026 CleanTec Systems — v1.0",
  primary_color: "#4F46E5",
  accent_color: "#38BDF8",
  dark_color: "#0EA5E9",
  logo_scale: 1.0,
  text_scale: 1.0,
  logo_url: null,
  hero_url: null,
  favicon_url: null,
};

function darkenHex(hex, amount = 0.15) {
  try {
    const h = hex.replace("#", "");
    const r = Math.max(0, Math.round(parseInt(h.slice(0, 2), 16) * (1 - amount)));
    const g = Math.max(0, Math.round(parseInt(h.slice(2, 4), 16) * (1 - amount)));
    const b = Math.max(0, Math.round(parseInt(h.slice(4, 6), 16) * (1 - amount)));
    return `#${r.toString(16).padStart(2, "0")}${g.toString(16).padStart(2, "0")}${b.toString(16).padStart(2, "0")}`;
  } catch {
    return hex;
  }
}

function applyThemeVars(b) {
  const root = document.documentElement;
  root.style.setProperty("--indaco", b.primary_color);
  root.style.setProperty("--indaco-dark", darkenHex(b.primary_color, 0.15));
  root.style.setProperty("--celeste", b.accent_color);
  root.style.setProperty("--azzurro", b.dark_color);
  root.style.setProperty("--logo-scale", String(b.logo_scale || 1));
  root.style.setProperty("--text-scale", String(b.text_scale || 1));
}

function applyTabMeta(b) {
  if (b.app_name) {
    document.title = `${b.app_name} — Control Room`;
  }
  if (b.favicon_url) {
    const url = `${BACKEND}${b.favicon_url}`;
    let link = document.querySelector("link[rel='icon']");
    if (!link) {
      link = document.createElement("link");
      link.rel = "icon";
      document.head.appendChild(link);
    }
    link.href = url;
  }
}

export function BrandingProvider({ children }) {
  const [branding, setBranding] = useState(DEFAULTS);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(`${BACKEND}/api/branding`);
      const merged = { ...DEFAULTS, ...data };
      setBranding(merged);
      applyThemeVars(merged);
      applyTabMeta(merged);
    } catch (e) {
      // fall back to defaults silently
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const reload = useCallback(() => load(), [load]);

  return (
    <BrandingContext.Provider value={{ branding, loaded, reload }}>
      {children}
    </BrandingContext.Provider>
  );
}

export function useBranding() {
  const ctx = useContext(BrandingContext);
  if (!ctx) return { branding: DEFAULTS, loaded: true, reload: () => {} };
  return ctx;
}
