import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { ClockCountdown, Warning, ArrowRight, X } from "@phosphor-icons/react";

export default function TrialBanner() {
  const { user } = useAuth();
  const [info, setInfo] = useState(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (!user || user.role === "cliente") return;
    // Only admin sees full link to billing; everyone else just sees banner text
    api.get("/tenants/me").then(({ data }) => setInfo(data)).catch(() => {});
  }, [user]);

  if (!info || dismissed || !user) return null;
  const t = info.tenant || {};
  // Don't show for demo tenant (active indefinitely)
  if (t.is_demo) return null;
  const days = info.trial_days_left;
  const isTrial = t.stato === "trial";
  const isPastDue = t.stato === "past_due" || t.stato === "canceled" || t.stato === "suspended";
  if (!isTrial && !isPastDue) return null;

  const critical = (isTrial && days !== null && days <= 3) || isPastDue;

  return (
    <div className={`${critical ? "bg-red-600" : "bg-amber-500"} text-white text-sm py-2 px-4 flex items-center gap-3`} data-testid="trial-banner">
      {critical ? <Warning size={16} weight="fill" /> : <ClockCountdown size={16} weight="fill" />}
      <span className="flex-1">
        {isPastDue ? (
          <>Il tuo abbonamento è <strong>sospeso</strong>. Rinnova per tornare operativo.</>
        ) : days === 0 ? (
          <>La tua prova è <strong>scaduta oggi</strong>. Attiva l'abbonamento per continuare.</>
        ) : (
          <>Prova gratuita: <strong>{days} {days === 1 ? "giorno" : "giorni"}</strong> rimanenti. Attiva ora per non perdere i tuoi dati.</>
        )}
      </span>
      {user.role === "admin" && (
        <Link to="/billing" className="bg-white/20 hover:bg-white/30 px-3 py-1 rounded-md font-semibold inline-flex items-center gap-1" data-testid="trial-banner-cta">
          Attiva <ArrowRight size={12} />
        </Link>
      )}
      {!critical && (
        <button onClick={() => setDismissed(true)} className="opacity-70 hover:opacity-100" data-testid="trial-banner-dismiss">
          <X size={14} />
        </button>
      )}
    </div>
  );
}
