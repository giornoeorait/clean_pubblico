import React, { useCallback, useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, BarChart, Bar } from "recharts";
import { TrendUp, TrendDown, ChartLineUp, Drop, CurrencyEur, CircleNotch } from "@phosphor-icons/react";

const TREND_ICON = { crescita: TrendUp, calo: TrendDown, stabile: ChartLineUp };
const TREND_COLOR = { crescita: "bg-emerald-500", calo: "bg-red-500", stabile: "bg-slate-500" };

export default function Insights() {
  const [fc, setFc] = useState(null);
  const [cd, setCd] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(async () => {
    try {
      const [a, b] = await Promise.all([
        api.get("/insights/forecast?history_days=21&forecast_days=7"),
        api.get("/insights/consumi-detergenti?days=30"),
      ]);
      setFc(a.data); setCd(b.data);
    } catch { /* no-op */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  if (loading) return <div className="p-8 text-slate-400 flex items-center gap-2"><CircleNotch className="animate-spin" /> Analisi in corso…</div>;
  if (!fc) return <div className="p-8 text-slate-500">Nessun dato disponibile</div>;

  const chartData = [
    ...fc.history.map(h => ({ giorno: h.giorno, storico: h.kg, forecast: null })),
    ...fc.forecast.map(f => ({ giorno: f.giorno, storico: null, forecast: f.kg })),
  ];

  const Trend = TREND_ICON[fc.trend] || ChartLineUp;

  return (
    <div>
      <PageHeader
        eyebrow="Business Intelligence"
        title="Previsione carichi & Consumi"
        subtitle="Analisi trend produzione e costo detergenti. Forecast basato su regressione lineare degli ultimi 21 giorni."
      />

      {/* KPI forecast */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div className="kpi-card" data-testid="ins-avg">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-xl bg-indaco/10 flex items-center justify-center text-indaco"><ChartLineUp size={20} weight="duotone" /></div>
            <div>
              <div className="overline">Media storica</div>
              <div className="font-display text-2xl font-bold">{fc.avg_kg_day.toLocaleString("it-IT")}</div>
              <div className="text-xs text-slate-500">kg/giorno ultimi 21gg</div>
            </div>
          </div>
        </div>
        <div className="kpi-card" data-testid="ins-trend">
          <div className="flex items-start gap-3">
            <div className={`w-10 h-10 rounded-xl ${TREND_COLOR[fc.trend]} text-white flex items-center justify-center`}><Trend size={20} weight="duotone" /></div>
            <div>
              <div className="overline">Trend previsto</div>
              <div className="font-display text-2xl font-bold capitalize">{fc.trend}</div>
              <div className="text-xs text-slate-500">prossimi 7 giorni</div>
            </div>
          </div>
        </div>
        <div className="kpi-card" data-testid="ins-forecast">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-500 text-white flex items-center justify-center"><TrendUp size={20} weight="duotone" /></div>
            <div>
              <div className="overline">Atteso settimana prox.</div>
              <div className="font-display text-2xl font-bold">{fc.expected_next_week_kg.toLocaleString("it-IT")}</div>
              <div className="text-xs text-slate-500">kg totali</div>
            </div>
          </div>
        </div>
        <div className="kpi-card" data-testid="ins-cost-kg">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-500 text-white flex items-center justify-center"><CurrencyEur size={20} weight="duotone" /></div>
            <div>
              <div className="overline">Costo detergenti /kg</div>
              <div className="font-display text-2xl font-bold">€ {cd?.costo_per_kg?.toFixed(3) || "—"}</div>
              <div className="text-xs text-slate-500">30gg</div>
            </div>
          </div>
        </div>
      </div>

      {/* Forecast chart */}
      <div className="kpi-card mb-6">
        <div className="flex items-center gap-2 mb-4">
          <h3 className="font-display text-lg font-bold">Produzione — Storico & Forecast</h3>
          <span className="text-xs font-mono text-slate-400">kg/giorno</span>
        </div>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="giorno" fontSize={11} />
            <YAxis fontSize={11} />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="storico" stroke="#6366f1" strokeWidth={2} dot={{ r: 3 }} name="Storico" />
            <Line type="monotone" dataKey="forecast" stroke="#10b981" strokeWidth={2} strokeDasharray="5 5" dot={{ r: 3 }} name="Previsione" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Consumi */}
      {cd && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="kpi-card">
            <div className="flex items-center gap-2 mb-3">
              <Drop size={22} className="text-indaco" weight="duotone" />
              <h4 className="font-display text-lg font-bold">Consumo detergenti 30gg</h4>
            </div>
            <div className="space-y-3 text-sm">
              <div className="flex justify-between"><span className="text-slate-500">Kg lavati</span><span className="font-mono font-bold">{cd.total_kg_lavati.toLocaleString("it-IT")}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Detergenti usati</span><span className="font-mono font-bold">{cd.total_qta_detergenti}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Ratio u/kg</span><span className="font-mono font-bold">{cd.ratio_detergenti_per_kg}</span></div>
              <div className="flex justify-between pt-2 border-t border-slate-200"><span className="text-slate-500">Costo stimato</span><span className="font-display font-bold text-indaco">€ {cd.costo_stimato.toFixed(2)}</span></div>
            </div>
          </div>
          <div className="kpi-card col-span-1 lg:col-span-2">
            <h4 className="font-display text-lg font-bold mb-3">Top consumi per articolo</h4>
            {cd.top_consumi.length === 0 ? (
              <div className="text-center py-8 text-slate-400 text-sm">Nessun movimento detergenti registrato</div>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={cd.top_consumi} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis type="number" fontSize={11} />
                  <YAxis type="category" dataKey="codice" fontSize={11} width={90} />
                  <Tooltip />
                  <Bar dataKey="quantita" fill="#6366f1" name="Quantità" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
