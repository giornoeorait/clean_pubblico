import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import StatoBadge from "../components/StatoBadge";
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, BarChart, Bar, Cell } from "recharts";
import { Drop, Package, Factory, Truck, Receipt, Warning, TrendUp, CheckCircle } from "@phosphor-icons/react";
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
  const [lotti, setLotti] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [k, l] = await Promise.all([api.get("/dashboard/kpi"), api.get("/lotti?limit=10")]);
        setKpi(k.data);
        setLotti(l.data);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return <div className="text-slate-400 font-mono text-sm">Caricamento KPI…</div>;
  }

  const colors = ["#0EA5E9", "#38BDF8", "#4F46E5", "#6366F1", "#0284C7", "#7C3AED", "#8B5CF6", "#10B981", "#059669"];

  return (
    <div>
      <PageHeader
        eyebrow={`Benvenuto, ${user.name?.split(" ")[0]}`}
        title="Control Room"
        subtitle="Panoramica real-time della produzione, logistica e vendite."
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <KpiCard icon={Drop} label="Kg lavorati oggi" value={`${kpi.kg_oggi} kg`} hint="aggiornato in tempo reale" accent="azzurro" testId="kpi-kg-oggi" />
        <KpiCard icon={Package} label="Lotti attivi" value={kpi.lotti_attivi} hint={`${kpi.lotti_totali} totali`} accent="indaco" testId="kpi-lotti-attivi" />
        <KpiCard icon={Factory} label="Macchine in uso" value={`${kpi.macchine_in_uso}/${kpi.macchine_totali}`} hint={`${kpi.macchine_disponibili} disponibili`} accent="celeste" testId="kpi-macchine" />
        <KpiCard icon={Warning} label="NC aperte" value={kpi.nc_aperte} hint="controllo qualità" accent="indaco" testId="kpi-nc" />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <KpiCard icon={Truck} label="Consegne oggi" value={kpi.consegne_oggi} accent="azzurro" testId="kpi-consegne-oggi" />
        <KpiCard icon={CheckCircle} label="Puntualità" value={`${kpi.puntualita_pct}%`} hint="consegne consegnate" accent="celeste" testId="kpi-puntualita" />
        <KpiCard icon={Receipt} label="Fatturato mese" value={`€ ${kpi.fatturato_mese.toLocaleString("it-IT")}`} accent="indaco" testId="kpi-fatturato" />
        <KpiCard icon={TrendUp} label="Efficienza" value="94%" hint="media 7gg" accent="azzurro" testId="kpi-efficienza" />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-8">
        <div className="lg:col-span-2 kpi-card" data-testid="chart-trend-kg">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="overline">Produzione ultimi 7 giorni</div>
              <div className="font-display text-xl font-bold mt-1">Kg lavorati</div>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={kpi.trend_kg_7gg}>
              <defs>
                <linearGradient id="kgfill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#0EA5E9" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="#0EA5E9" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#E2E8F0" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="giorno" stroke="#94A3B8" fontSize={12} fontFamily="IBM Plex Mono" />
              <YAxis stroke="#94A3B8" fontSize={12} fontFamily="IBM Plex Mono" />
              <Tooltip contentStyle={{ background: "#0F172A", border: "none", borderRadius: 8, color: "white", fontFamily: "IBM Plex Mono", fontSize: 12 }} />
              <Area type="monotone" dataKey="kg" stroke="#0EA5E9" strokeWidth={2.5} fill="url(#kgfill)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="kpi-card" data-testid="chart-stati">
          <div className="overline mb-1">Distribuzione lotti</div>
          <div className="font-display text-xl font-bold mb-4">Per stato</div>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={kpi.stati_distribution} layout="vertical" margin={{ left: 60 }}>
              <CartesianGrid stroke="#E2E8F0" horizontal={false} strokeDasharray="3 3" />
              <XAxis type="number" stroke="#94A3B8" fontSize={11} fontFamily="IBM Plex Mono" />
              <YAxis dataKey="stato" type="category" stroke="#94A3B8" fontSize={11} fontFamily="IBM Plex Mono" width={90} />
              <Tooltip contentStyle={{ background: "#0F172A", border: "none", borderRadius: 8, color: "white", fontSize: 12 }} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {kpi.stati_distribution.map((_, i) => <Cell key={i} fill={colors[i % colors.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Recent lots */}
      <div className="kpi-card" data-testid="recent-lotti">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="overline">Attività recente</div>
            <div className="font-display text-xl font-bold mt-1">Ultimi lotti</div>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Lotto</th>
                <th>Cliente</th>
                <th>Quantità</th>
                <th>Peso</th>
                <th>Priorità</th>
                <th>Stato</th>
              </tr>
            </thead>
            <tbody>
              {lotti.slice(0, 8).map((l) => (
                <tr key={l.id}>
                  <td className="font-mono text-xs">{l.numero}</td>
                  <td className="text-slate-600 text-xs">{l.cliente_id.slice(0, 8)}…</td>
                  <td className="font-mono">{l.quantita}</td>
                  <td className="font-mono">{l.peso} kg</td>
                  <td><StatoBadge stato={l.priorita} /></td>
                  <td><StatoBadge stato={l.stato_corrente} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
