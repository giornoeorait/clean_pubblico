import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../lib/api";
import { Sparkle, CheckCircle, Crown, Star } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";

const PLAN_ICON = { starter: Star, pro: Crown, enterprise: Sparkle };
const FEATURE_LABELS = {
  crud_base: "Anagrafiche & CRUD completo",
  mes: "MES Produzione",
  kanban: "Kanban drag & drop",
  tracciabilita: "Tracciabilità lotti (9 stati)",
  fatture: "Fatturazione",
  dashboard: "KPI Dashboard & trend",
  portale_cliente: "Portale Cliente",
  starter: "Tutto di Starter",
  magazzino: "Magazzino detergenti/DPI",
  manutenzione: "Manutenzione macchine",
  notifiche_sms: "Notifiche SMS/WhatsApp",
  audit_log: "Audit log completo",
  pro: "Tutto di Pro",
  hardware_ingestion: "Integrazione bilance/scanner/RFID",
  multi_sede: "Multi-sede e multi-warehouse",
  sla_24_7: "SLA 24/7",
  priority_support: "Supporto prioritario",
};

export default function Pricing() {
  const navigate = useNavigate();
  const [plans, setPlans] = useState([]);
  const [cycle, setCycle] = useState("monthly");
  const [trialDays, setTrialDays] = useState(14);

  useEffect(() => {
    api.get("/plans").then(({ data }) => {
      setPlans(data.plans);
      setTrialDays(data.trial_days);
    }).catch(() => {});
  }, []);

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Nav */}
      <header className="sticky top-0 z-40 bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center">
          <Link to="/" className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-md bg-gradient-to-br from-azzurro to-indaco flex items-center justify-center">
              <Sparkle size={18} weight="fill" className="text-white" />
            </div>
            <div className="font-display font-bold text-lg tracking-tight">CleanTec</div>
          </Link>
          <nav className="ml-auto flex items-center gap-6 text-sm">
            <Link to="/pricing" className="text-indaco font-semibold">Prezzi</Link>
            <Link to="/login" className="text-slate-600 hover:text-indaco">Accedi</Link>
            <Button onClick={() => navigate("/register")} className="bg-indaco hover:bg-indaco-dark" data-testid="nav-register-btn">Prova Gratis</Button>
          </nav>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-16">
        <div className="text-center mb-12">
          <div className="overline text-indaco mb-3">PRICING</div>
          <h1 className="font-display text-4xl sm:text-5xl lg:text-6xl font-bold text-slate-900 tracking-tight">
            Scegli il piano adatto<br />alla tua lavanderia industriale.
          </h1>
          <p className="mt-5 text-slate-600 max-w-2xl mx-auto">
            {trialDays} giorni di prova gratuita. Senza carta di credito. Cancelli quando vuoi.
          </p>

          {/* Cycle toggle */}
          <div className="inline-flex items-center bg-white border border-slate-200 rounded-full p-1 mt-8" data-testid="cycle-toggle">
            <button
              onClick={() => setCycle("monthly")}
              className={`px-5 py-2 text-sm font-semibold rounded-full transition ${cycle === "monthly" ? "bg-indaco text-white" : "text-slate-600"}`}
              data-testid="cycle-monthly"
            >
              Mensile
            </button>
            <button
              onClick={() => setCycle("annual")}
              className={`px-5 py-2 text-sm font-semibold rounded-full transition flex items-center gap-2 ${cycle === "annual" ? "bg-indaco text-white" : "text-slate-600"}`}
              data-testid="cycle-annual"
            >
              Annuale <span className="text-[10px] bg-emerald-500 text-white px-1.5 py-0.5 rounded-full">-17%</span>
            </button>
          </div>
        </div>

        {/* Plans grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-12">
          {plans.map((p) => {
            const Icon = PLAN_ICON[p.id] || Star;
            const price = cycle === "annual" ? p.price_annual : p.price_monthly;
            const isHl = p.highlight;
            return (
              <div
                key={p.id}
                className={`relative rounded-2xl p-8 border ${isHl ? "bg-slate-900 text-white border-indaco shadow-2xl scale-105" : "bg-white border-slate-200"}`}
                data-testid={`plan-${p.id}`}
              >
                {isHl && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-indaco text-white px-3 py-1 text-[10px] font-bold rounded-full uppercase tracking-widest">
                    Più popolare
                  </div>
                )}
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center mb-4 ${isHl ? "bg-white/10" : "bg-indaco/10"}`}>
                  <Icon size={24} weight="duotone" className={isHl ? "text-celeste" : "text-indaco"} />
                </div>
                <div className="overline mb-1 opacity-60">{p.cta}</div>
                <h3 className="font-display text-2xl font-bold mb-3">{p.nome}</h3>
                <div className="flex items-baseline gap-1 mb-1">
                  <span className="font-display text-5xl font-bold">€{price}</span>
                  <span className={`text-sm ${isHl ? "text-slate-300" : "text-slate-500"}`}>/mese</span>
                </div>
                <div className={`text-xs font-mono mb-6 ${isHl ? "text-slate-300" : "text-slate-500"}`}>
                  {cycle === "annual" ? `€${(price * 12).toFixed(0)} all'anno` : "fatturato mensile"}
                </div>

                <ul className="space-y-2 text-sm mb-8">
                  {p.features.slice(0, 8).map((f) => (
                    <li key={f} className="flex items-start gap-2">
                      <CheckCircle size={16} weight="fill" className={isHl ? "text-celeste mt-0.5 flex-shrink-0" : "text-indaco mt-0.5 flex-shrink-0"} />
                      <span>{FEATURE_LABELS[f] || f}</span>
                    </li>
                  ))}
                </ul>

                <div className={`text-xs mb-6 space-y-1 ${isHl ? "text-slate-400" : "text-slate-500"}`}>
                  <div>👥 Utenti: {p.limits.users === -1 ? "Illimitati" : p.limits.users}</div>
                  <div>📦 Lotti/mese: {p.limits.lotti_monthly === -1 ? "Illimitati" : p.limits.lotti_monthly.toLocaleString("it-IT")}</div>
                  <div>📱 SMS inclusi: {p.limits.sms_monthly === 0 ? "Non incluso" : `${p.limits.sms_monthly}/mese`}</div>
                </div>

                {p.id === "enterprise" ? (
                  <Button className="w-full bg-white/10 hover:bg-white/20 text-white border border-white/20" data-testid={`plan-${p.id}-cta`}>
                    Contattaci
                  </Button>
                ) : (
                  <Button
                    onClick={() => navigate(`/register?plan=${p.id}&cycle=${cycle}`)}
                    className={`w-full ${isHl ? "bg-celeste hover:bg-celeste/80 text-slate-900" : "bg-indaco hover:bg-indaco-dark text-white"}`}
                    data-testid={`plan-${p.id}-cta`}
                  >
                    Inizia {trialDays} giorni gratis
                  </Button>
                )}
              </div>
            );
          })}
        </div>

        <div className="text-center mt-12 text-sm text-slate-500">
          Tutti i prezzi sono IVA esclusa. Pagamenti sicuri tramite Stripe. Cancella in qualsiasi momento.
        </div>
      </main>
    </div>
  );
}
