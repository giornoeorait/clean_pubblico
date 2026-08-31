import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, LineChart, Line, BarChart, Bar, Legend } from "recharts";
import { Users, Truck, Receipt, Warning, TrendUp, CheckCircle, CurrencyEur, ChartLineUp, Archive, Scales } from "@phosphor-icons/react";
import { useAuth } from "../context/AuthContext";
import { usePermissions } from "../lib/permissions";

const MESI_LBL = { 1: "Gen", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mag", 6: "Giu", 7: "Lug", 8: "Ago", 9: "Set", 10: "Ott", 11: "Nov", 12: "Dic" };

// kg → quintali/tonnellate (mai kg)
const fmtPeso = (kg) => {
  const v = Number(kg) || 0;
  if (Math.abs(v) >= 1000) return `${(v / 1000).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} t`;
  return `${(v / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} q`;
};

const KpiCard = ({ icon: Icon, label, value, hint, accent = "indaco", testId, badge }) => (
  <div className="kpi-card" data-testid={testId}>
    <div className="flex items-start justify-between">
      <div>
        <div className="overline flex items-center gap-1.5">
          {label}
          {badge && <span className="text-[9px] font-mono uppercase bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded">{badge}</span>}
        </div>
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
  const { canSeePrices } = usePermissions();
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
        {canSeePrices && (
          <>
            <KpiCard icon={Receipt} label="Fatturato mese" value={`€ ${kpi.fatturato_mese.toLocaleString("it-IT", {minimumFractionDigits: 2})}`} hint={`Incassato: € ${kpi.incassato_mese.toLocaleString("it-IT", {minimumFractionDigits: 2})}`} testId="kpi-fatturato" />
            <KpiCard icon={CurrencyEur} label="Sospesi" value={`€ ${kpi.sospesi_totale.toLocaleString("it-IT", {minimumFractionDigits: 2})}`} hint={`${kpi.sospesi_count} fatture da incassare`} accent="amber-500" testId="kpi-sospesi" />
          </>
        )}
      </div>

      {canSeePrices && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <KpiCard
            icon={ChartLineUp}
            label="Da fatturare mese corrente"
            value={`€ ${kpi.fatturare_mese_importo.toLocaleString("it-IT", { minimumFractionDigits: 2 })}`}
            hint={`${kpi.fatturare_mese_count} DDT prodotti non ancora fatturati`}
            accent="celeste"
            testId="kpi-da-fatturare-mese"
          />
          <KpiCard
            icon={Archive}
            label={`Fatturato ${kpi.anno_corrente}`}
            value={`€ ${kpi.fatturato_anno.toLocaleString("it-IT", { minimumFractionDigits: 2 })}`}
            hint={kpi.fatturato_anno_storico > 0
              ? `Fatture: € ${kpi.fatturato_anno_fatture.toLocaleString("it-IT", { minimumFractionDigits: 2 })} · Storico: € ${kpi.fatturato_anno_storico.toLocaleString("it-IT", { minimumFractionDigits: 2 })}`
              : `Solo fatture emesse · nessun mese storico integrato`
            }
            badge={kpi.fatturato_anno_storico > 0 ? "incl. storico" : null}
            testId="kpi-fatturato-anno"
          />
          {kpi.storico_mesi_inclusi && kpi.storico_mesi_inclusi.length > 0 && (
            <div className="kpi-card lg:col-span-2" data-testid="storico-info">
              <div className="flex items-start justify-between">
                <div>
                  <div className="overline">Mesi storici inclusi nelle statistiche</div>
                  <div className="font-display text-base font-semibold text-slate-900 mt-2">
                    {kpi.storico_mesi_inclusi.map(m => MESI_LBL[m]).join(" · ")} {kpi.anno_corrente}
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    Totale storico anno: <b className="font-mono">€ {kpi.storico_totale_anno.toLocaleString("it-IT", { minimumFractionDigits: 2 })}</b>
                    {" · "}Aggiunto a dashboard: <b className="font-mono">€ {kpi.fatturato_anno_storico.toLocaleString("it-IT", { minimumFractionDigits: 2 })}</b>
                  </div>
                  <div className="text-[11px] text-slate-400 mt-1">
                    Sono esclusi mesi per i quali esistono fatture vere (no doppi conteggi).
                  </div>
                </div>
                <div className="w-11 h-11 rounded-lg flex items-center justify-center bg-emerald-100">
                  <Archive size={22} weight="duotone" className="text-emerald-700" />
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Produzione in chilogrammi */}
      {kpi.kg_mese && (
        <div className="mb-6" data-testid="dashboard-produzione-kg">
          <div className="flex items-center gap-2 mb-3">
            <Scales size={20} className="text-emerald-600" weight="duotone" />
            <h3 className="font-display text-lg font-bold">Produzione (quintali / tonnellate)</h3>
          </div>
          {/* KPI mese */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
            <div className="kpi-card">
              <div className="overline">Mese corrente</div>
              <div className="font-display text-3xl font-bold text-emerald-700 mt-1" data-testid="kg-mese-totale">
                {fmtPeso(kpi.kg_mese.totale)}
              </div>
              <div className="text-xs text-slate-500 mt-1">Prodotti in {MESI_LBL[new Date().getMonth() + 1] || "mese"}</div>
            </div>
            <div className="kpi-card bg-sky-50 border-l-4 border-sky-300">
              <div className="overline text-sky-700">Biancheria piana</div>
              <div className="font-display text-2xl font-bold text-sky-700 mt-1" data-testid="kg-mese-biancheria">
                {fmtPeso(kpi.kg_mese.biancheria_piana)}
              </div>
            </div>
            <div className="kpi-card bg-emerald-50 border-l-4 border-emerald-300">
              <div className="overline text-emerald-700">Spugna</div>
              <div className="font-display text-2xl font-bold text-emerald-700 mt-1" data-testid="kg-mese-spugna">
                {fmtPeso(kpi.kg_mese.spugna)}
              </div>
            </div>
            <div className="kpi-card bg-violet-50 border-l-4 border-violet-300">
              <div className="overline text-violet-700">Varie</div>
              <div className="font-display text-2xl font-bold text-violet-700 mt-1" data-testid="kg-mese-varie">
                {fmtPeso(kpi.kg_mese.varie)}
              </div>
            </div>
            <div className="kpi-card">
              <div className="overline">Anno {kpi.anno_corrente}</div>
              <div className="font-display text-2xl font-bold text-indaco mt-1" data-testid="kg-anno-totale">
                {fmtPeso(kpi.kg_anno.totale)}
              </div>
              <div className="text-[11px] text-slate-500 mt-1 leading-snug">
                Bianch.: <span className="font-mono text-sky-700">{fmtPeso(kpi.kg_anno.biancheria_piana)}</span>{" "}·{" "}
                Spugna: <span className="font-mono text-emerald-700">{fmtPeso(kpi.kg_anno.spugna)}</span>{" "}·{" "}
                Varie: <span className="font-mono text-violet-700">{fmtPeso(kpi.kg_anno.varie)}</span>
              </div>
            </div>
          </div>
          {/* Grafico mensile con confronto categorie (ultimi 12 mesi) */}
          {Array.isArray(kpi.kg_serie_mensile) && kpi.kg_serie_mensile.length > 0 && (
            <div className="kpi-card" data-testid="kg-serie-chart">
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm font-semibold text-slate-700">
                  Andamento mensile produzione (ultimi 12 mesi) — confronto tra categorie
                </div>
                <div className="text-[11px] text-slate-500 italic">Barre impilate = totale mensile</div>
              </div>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={kpi.kg_serie_mensile}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="mese" fontSize={11} tick={{ fill: "#64748b" }} />
                  <YAxis fontSize={11} tick={{ fill: "#64748b" }} tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toLocaleString("it-IT")} t` : `${(v / 100).toLocaleString("it-IT")} q`} />
                  <Tooltip
                    formatter={(v, name) => [fmtPeso(v), name]}
                    contentStyle={{ borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 12 }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="biancheria_piana" stackId="a" name="Biancheria piana" fill="#0ea5e9" />
                  <Bar dataKey="spugna" stackId="a" name="Spugna" fill="#10b981" />
                  <Bar dataKey="varie" stackId="a" name="Varie" fill="#8b5cf6" />
                  <Bar dataKey="non_classificato" stackId="a" name="Non classificato" fill="#f59e0b" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      {/* Mini-trend: valore cumulato giorno per giorno dei DDT non ancora fatturati */}
      {canSeePrices && Array.isArray(kpi.fatturare_mese_serie_cumul) && kpi.fatturare_mese_serie_cumul.length > 0 && (
        <div className="kpi-card mb-6" data-testid="trend-da-fatturare">
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <ChartLineUp size={20} className="text-celeste" weight="duotone" />
              <h3 className="font-display text-lg font-bold">Produzione economica cumulata · mese corrente</h3>
            </div>
            <span className="text-xs text-slate-500 font-mono">
              Valore residuo da fatturare: <b className="text-celeste">€ {kpi.fatturare_mese_importo.toLocaleString("it-IT", { minimumFractionDigits: 2 })}</b>
            </span>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={kpi.fatturare_mese_serie_cumul}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="giorno" fontSize={10} tick={{ fill: "#64748b" }} />
              <YAxis fontSize={10} tickFormatter={(v) => `€ ${v.toLocaleString("it-IT")}`} tick={{ fill: "#64748b" }} />
              <Tooltip
                formatter={(v, name) => [
                  `€ ${Number(v).toLocaleString("it-IT", { minimumFractionDigits: 2 })}`,
                  name === "cumulato" ? "Cumulato" : "Valore giorno"
                ]}
                contentStyle={{ borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 12 }}
              />
              <Line type="monotone" dataKey="cumulato" stroke="#0ea5e9" strokeWidth={2.5} dot={{ r: 3 }} activeDot={{ r: 5 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

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
            {canSeePrices && (
              <>
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
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
