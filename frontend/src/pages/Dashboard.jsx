import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip } from "recharts";
import { Users, Package, Truck, Receipt, Warning, TrendUp, CheckCircle, CurrencyEur } from "@phosphor-icons/react";
import { useAuth } from "../context/AuthContext";

const KpiCard = ({ icon: Icon, label, value, hint, accent = "indaco", testId }) => (
  <div className="kpi-card" data-testid={testId}>
    <div className="flex items-start justify-between">
      <div>
        <div className="overline">{label}</div>
        <div className="font-display text-3xl font-bold text-slate-900 mt-2 tracking-tight" data-testid={`${testId}-value`}>{value}</div>
        {hint && <div className="text-xs text-slate-500 mt-1 font-mono">{hint}</div>}
      </div>
      <div className={`w-11 h-11 rounded-lg flex items-center justify-center bg-${accent}/10`}>
        <Icon size={22} weight="duotone" className={`text-${accent}`} />
      </div>
    </div>
  </div>
);

export default function Dashboard() {
  const { user } = useAuth();
  const [kpi, setKpi] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/dashboard/kpi");
        setKpi(data);
      } finally { setLoading(false); }
    })();
  }, []);

  if (loading) return <div className="text-slate-400 font-mono text-sm">Caricamento KPI…</div>;

  return (
    <div>
      <PageHeader
        eyebrow={`Benvenuto, ${user?.name || "utente"}`}
        title="Dashboard operativa"
        subtitle="Flusso DDT → Fatturazione → Incassi. Stato attuale del tuo business."
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <KpiCard icon={Users} label="Clienti" value={kpi.clienti_totali} hint={`${kpi.articoli_totali} articoli · ${kpi.listini_attivi} listini attivi`} testId="kpi-clienti" />
        <KpiCard icon={Truck} label="DDT questo mese" value={kpi.ddt_mese} hint={`${kpi.ddt_oggi} oggi · ${kpi.ddt_non_fatturati} da fatturare`} accent="celeste" testId="kpi-ddt" />
        <KpiCard icon={Receipt} label="Fatturato mese" value={`€ ${kpi.fatturato_mese.toLocaleString("it-IT", {minimumFractionDigits: 2})}`} hint={`Incassato: € ${kpi.incassato_mese.toLocaleString("it-IT", {minimumFractionDigits: 2})}`} testId="kpi-fatturato" />
        <KpiCard icon={CurrencyEur} label="Sospesi" value={`€ ${kpi.sospesi_totale.toLocaleString("it-IT", {minimumFractionDigits: 2})}`} hint={`${kpi.sospesi_count} fatture da incassare`} accent="amber-500" testId="kpi-sospesi" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="kpi-card lg:col-span-2">
          <div className="flex items-center gap-2 mb-3">
            <TrendUp size={20} className="text-indaco" weight="duotone" />
            <h3 className="font-display text-lg font-bold">DDT ultimi 7 giorni</h3>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={kpi.trend_ddt_7gg}>
              <defs>
                <linearGradient id="ddtGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4}/>
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="giorno" fontSize={11} />
              <YAxis fontSize={11} />
              <Tooltip />
              <Area type="monotone" dataKey="ddt" stroke="#6366f1" strokeWidth={2} fill="url(#ddtGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="kpi-card">
          <div className="flex items-center gap-2 mb-3">
            <Warning size={20} className="text-amber-500" weight="duotone" />
            <h3 className="font-display text-lg font-bold">Alert commerciali</h3>
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 bg-indaco/10 rounded-md">
              <div className="flex items-center gap-2">
                <Truck size={18} className="text-indaco" weight="duotone" />
                <span className="text-sm">DDT non fatturati</span>
              </div>
              <span className="font-display text-2xl font-bold text-indaco">{kpi.ddt_non_fatturati}</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-amber-50 rounded-md">
              <div className="flex items-center gap-2">
                <CurrencyEur size={18} className="text-amber-600" weight="duotone" />
                <span className="text-sm">Fatture da incassare</span>
              </div>
              <span className="font-display text-2xl font-bold text-amber-600">{kpi.sospesi_count}</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-emerald-50 rounded-md">
              <div className="flex items-center gap-2">
                <CheckCircle size={18} className="text-emerald-600" weight="duotone" />
                <span className="text-sm">Incassato nel mese</span>
              </div>
              <span className="font-display text-lg font-bold text-emerald-600">€ {kpi.incassato_mese.toLocaleString("it-IT", {minimumFractionDigits: 2})}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
