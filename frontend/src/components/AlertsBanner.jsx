import React, { useEffect, useState } from "react";
import api from "../lib/api";
import { WarningCircle, X, Bell } from "@phosphor-icons/react";
import { useNavigate } from "react-router-dom";

const SEV_STYLES = {
  error: "border-red-300 bg-red-50 text-red-800",
  warning: "border-amber-300 bg-amber-50 text-amber-800",
  info: "border-sky-300 bg-sky-50 text-sky-800",
};

const TARGETS = {
  fattura_scaduta: "/fornitori/fatture",
  fattura_scadenza: "/fornitori/fatture",
  aging_sospeso: "/sospesi",
  costo_soglia: "/costi",
};

export default function AlertsBanner() {
  const [data, setData] = useState(null);
  const [dismissed, setDismissed] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    let mounted = true;
    const fetch = async () => {
      try {
        const { data } = await api.get("/alerts");
        if (mounted) setData(data);
      } catch { /* silent */ }
    };
    fetch();
    const id = setInterval(fetch, 5 * 60 * 1000); // ogni 5 min
    return () => { mounted = false; clearInterval(id); };
  }, []);

  if (!data || dismissed || data.totale === 0) return null;

  const critical = data.alerts.filter(a => a.severity === "error");
  const warnings = data.alerts.filter(a => a.severity === "warning");
  const showList = expanded ? data.alerts : (critical.length ? critical.slice(0, 3) : warnings.slice(0, 2));
  const topSev = critical.length ? "error" : warnings.length ? "warning" : "info";

  return (
    <div className={`border-b ${SEV_STYLES[topSev]} sticky top-0 z-30`} data-testid="alerts-banner">
      <div className="px-4 py-2 flex items-start gap-3">
        <div className="flex-shrink-0 pt-0.5">
          {topSev === "error" ? <WarningCircle size={20} weight="fill" /> : <Bell size={20} weight="fill" />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 text-sm font-bold">
            {data.totale} {data.totale === 1 ? "alert" : "alert"} attivi
            {critical.length > 0 && <span className="px-1.5 py-0.5 rounded bg-red-600 text-white text-[10px]">{critical.length} URGENTI</span>}
            {warnings.length > 0 && <span className="px-1.5 py-0.5 rounded bg-amber-500 text-white text-[10px]">{warnings.length} avvisi</span>}
          </div>
          <ul className="text-xs mt-1 space-y-0.5">
            {showList.map((a, i) => (
              <li key={i} className="flex items-start gap-2">
                <span>•</span>
                <button onClick={() => TARGETS[a.tipo] && navigate(TARGETS[a.tipo])}
                  className="text-left hover:underline flex-1" data-testid={`alert-${a.tipo}-${i}`}>
                  {a.messaggio}
                </button>
              </li>
            ))}
            {!expanded && data.totale > showList.length && (
              <li><button onClick={() => setExpanded(true)} className="text-xs underline" data-testid="alerts-expand">
                … mostra tutti i {data.totale} alert
              </button></li>
            )}
          </ul>
        </div>
        <button onClick={() => setDismissed(true)} className="flex-shrink-0 p-1 hover:bg-white/30 rounded" title="Chiudi" data-testid="alerts-dismiss">
          <X size={16} />
        </button>
      </div>
    </div>
  );
}
