import React, { useEffect, useState, useCallback } from "react";
import api from "../lib/api";
import { ArrowsClockwise, Sparkle } from "@phosphor-icons/react";

const POLL_INTERVAL_MS = 60_000; // 60s

/**
 * Polls /api/version periodically. If the server version differs from the one
 * captured on first load, shows a sticky banner inviting the user to reload.
 *
 * Also exposes a small "v.xxx" badge for the current version (rendered via context).
 */

export const VersionContext = React.createContext({ version: null });

export function VersionProvider({ children }) {
  const [initialVersion, setInitialVersion] = useState(null);
  const [serverVersion, setServerVersion] = useState(null);
  const [dismissed, setDismissed] = useState(false);

  const fetchVersion = useCallback(async () => {
    try {
      const { data } = await api.get("/version");
      setServerVersion(data.version);
      if (initialVersion === null) {
        setInitialVersion(data.version);
      }
    } catch {
      /* ignore network errors */
    }
  }, [initialVersion]);

  useEffect(() => {
    fetchVersion();
    const id = setInterval(fetchVersion, POLL_INTERVAL_MS);
    // Also re-check when the tab becomes visible again
    const onVis = () => { if (document.visibilityState === "visible") fetchVersion(); };
    document.addEventListener("visibilitychange", onVis);
    return () => { clearInterval(id); document.removeEventListener("visibilitychange", onVis); };
  }, [fetchVersion]);

  const hasUpdate = initialVersion && serverVersion && initialVersion !== serverVersion && !dismissed;

  const doReload = () => {
    try {
      // Clear caches the browser controls
      if (window.caches) {
        caches.keys().then(keys => keys.forEach(k => caches.delete(k)));
      }
    } catch { /* ignore */ }
    // Append a timestamp to defeat any disk cache on index.html
    const url = new URL(window.location.href);
    url.searchParams.set("_v", Date.now().toString());
    window.location.replace(url.toString());
  };

  return (
    <VersionContext.Provider value={{ version: serverVersion || initialVersion }}>
      {hasUpdate && (
        <div
          data-testid="version-update-banner"
          className="fixed top-3 left-1/2 -translate-x-1/2 z-[100] bg-gradient-to-r from-indaco to-celeste text-white shadow-lg rounded-full px-4 py-2 flex items-center gap-3 animate-pulse-once"
        >
          <Sparkle size={16} weight="fill" className="text-yellow-200" />
          <span className="text-sm font-medium">Nuova versione disponibile</span>
          <button
            onClick={doReload}
            data-testid="version-reload-btn"
            className="text-xs bg-white/20 hover:bg-white/30 px-3 py-1 rounded-full flex items-center gap-1 transition"
          >
            <ArrowsClockwise size={12} weight="bold" />
            Ricarica
          </button>
          <button
            onClick={() => setDismissed(true)}
            data-testid="version-dismiss-btn"
            className="text-xs text-white/70 hover:text-white"
            aria-label="Chiudi"
          >
            ✕
          </button>
        </div>
      )}
      {children}
    </VersionContext.Provider>
  );
}

export function VersionBadge() {
  const { version } = React.useContext(VersionContext);
  if (!version) return null;
  return (
    <span data-testid="version-badge" className="text-[10px] font-mono text-slate-500 opacity-60">
      v.{version}
    </span>
  );
}
