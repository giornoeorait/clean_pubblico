import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { ChartBar, CurrencyEur, Scales, Gauge, Clock, Truck, TrendUp } from "@phosphor-icons/react";
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, CartesianGrid,
} from "recharts";

const COLORS = ["#4f46e5", "#0ea5e9", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6"];
const fmtE = (n) => `€ ${(n || 0).toFixed(2)}`;
const fmtK = (n) => `${(n || 0).toFixed(1)} kg`;

const TABS = [
  { v: "fatturato", l: "Fatturato", icon: CurrencyEur },
  { v: "produzione", l: "Produzione (kg)", icon: Scales },
  { v: "costo_kg", l: "Costo per kg", icon: Gauge },
  { v: "marginalita", l: "Marginalità", icon: TrendUp },
  { v: "aging", l: "Aging sospesi", icon: Clock },
  { v: "km", l: "Km automezzi", icon: Truck },
];

export default function Report() {
  const [tab, setTab] = useState("fatturato");
  const [anno, setAnno] = useState(new Date().getFullYear());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchReport = async () => {
    setLoading(true); setData(null);
    try {
      const path = tab === "aging" ? "/reports/aging-sospesi" :
                   tab === "km" ? `/reports/km-automezzi?anno=${anno}` :
                   tab === "costo_kg" ? `/reports/costo-kg?anno=${anno}` :
                   tab === "fatturato" ? `/reports/fatturato?anno=${anno}` :
                   tab === "produzione" ? `/reports/produzione?anno=${anno}` :
                   `/reports/marginalita?anno=${anno}`;
      const { data: d } = await api.get(path);
      setData(d);
    } finally { setLoading(false); }
  };
  useEffect(() => { fetchReport(); }, [tab, anno]);

  return (
    <div>
      <PageHeader
        eyebrow="Business Intelligence"
        title="Report & Statistiche"
        subtitle="Fatturato, produzione, costi, marginalità e aging aggregati per mese, cliente, articolo e automezzo."
        actions={
          <Select value={String(anno)} onValueChange={v => setAnno(Number(v))}>
            <SelectTrigger className="w-28" data-testid="report-anno"><SelectValue /></SelectTrigger>
            <SelectContent>
              {[anno - 2, anno - 1, anno, anno + 1].map(y => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}
            </SelectContent>
          </Select>
        }
      />

      <div className="flex gap-1 border-b border-slate-200 mb-6 overflow-x-auto">
        {TABS.map(t => {
          const Icon = t.icon;
          return (
            <button key={t.v} onClick={() => setTab(t.v)}
              className={`px-4 py-2 text-sm font-medium whitespace-nowrap flex items-center gap-2 border-b-2 transition ${tab === t.v ? "border-indaco text-indaco" : "border-transparent text-slate-500 hover:text-slate-700"}`}
              data-testid={`report-tab-${t.v}`}>
              <Icon size={16} />{t.l}
            </button>
          );
        })}
      </div>

      {loading && <div className="kpi-card p-8 text-center text-slate-400">Caricamento…</div>}

      {!loading && data && tab === "fatturato" && <FatturatoView d={data} />}
      {!loading && data && tab === "produzione" && <ProduzioneView d={data} />}
      {!loading && data && tab === "costo_kg" && <CostoKgView d={data} />}
      {!loading && data && tab === "marginalita" && <MarginalitaView d={data} />}
      {!loading && data && tab === "aging" && <AgingView d={data} />}
      {!loading && data && tab === "km" && <KmView d={data} />}
    </div>
  );
}

function Kpi({ label, value, sub, color = "text-indaco" }) {
  return (
    <div className="kpi-card p-4">
      <div className="text-[11px] uppercase tracking-wide text-slate-500 font-mono">{label}</div>
      <div className={`text-2xl md:text-3xl font-display font-bold ${color}`}>{value}</div>
      {sub && <div className="text-xs text-slate-400 mt-1">{sub}</div>}
    </div>
  );
}

// ============== FATTURATO ==============
function FatturatoView({ d }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi label="Totale fatturato" value={fmtE(d.totale)} sub={`anno ${d.anno || "—"}`} />
        <Kpi label="Incassato" value={fmtE(d.incassato)} color="text-emerald-600" />
        <Kpi label="Sospeso" value={fmtE(d.sospeso)} color="text-red-600" />
        <Kpi label="N° fatture" value={d.per_mese.reduce((s, m) => s + m.n, 0)} color="text-slate-900" />
      </div>

      <div className="kpi-card p-4">
        <h4 className="font-display font-bold mb-3">Andamento mensile</h4>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={d.per_mese}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="mese" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => fmtE(v)} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="incassato" stackId="a" fill="#10b981" name="Incassato" />
            <Bar dataKey="sospeso" stackId="a" fill="#ef4444" name="Sospeso" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="kpi-card p-0 overflow-hidden">
        <div className="px-4 py-3 border-b"><h4 className="font-display font-bold">Top 20 clienti per fatturato</h4></div>
        <div className="overflow-x-auto"><table className="data-table">
          <thead><tr><th>#</th><th>Cliente</th><th className="text-right">Fatturato</th><th className="text-right">N° fatture</th></tr></thead>
          <tbody>
            {d.per_cliente.map((c, i) => (
              <tr key={c.cliente_id || i}><td className="text-xs text-slate-400">{i + 1}</td><td>{c.cliente_nome}</td><td className="text-right font-mono font-bold">{fmtE(c.totale)}</td><td className="text-right text-xs">{c.n}</td></tr>
            ))}
            {d.per_cliente.length === 0 && <tr><td colSpan={4} className="text-center py-8 text-slate-400">Nessuna fattura nel periodo</td></tr>}
          </tbody>
        </table></div>
      </div>
    </div>
  );
}

// ============== PRODUZIONE ==============
function ProduzioneView({ d }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <Kpi label="Totale kg prodotti" value={fmtK(d.totale_kg)} sub={`anno ${d.anno || "—"}`} />
        <Kpi label="Totale pezzi" value={(d.totale_pezzi || 0).toFixed(0)} color="text-slate-900" />
        <Kpi label="Peso medio" value={d.totale_pezzi ? `${(d.totale_kg / d.totale_pezzi).toFixed(2)} kg/pz` : "—"} color="text-celeste" />
      </div>

      <div className="kpi-card p-4">
        <h4 className="font-display font-bold mb-3">Andamento kg per mese</h4>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={d.per_mese}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="mese" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v, n) => n === "kg" ? fmtK(v) : v} />
            <Line type="monotone" dataKey="kg" stroke="#4f46e5" strokeWidth={2} dot={{ r: 4 }} />
            <Line type="monotone" dataKey="pezzi" stroke="#0ea5e9" strokeDasharray="4 4" />
            <Legend wrapperStyle={{ fontSize: 12 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="kpi-card p-0 overflow-hidden">
          <div className="px-4 py-3 border-b"><h4 className="font-display font-bold">Top clienti (kg)</h4></div>
          <div className="overflow-x-auto"><table className="data-table">
            <thead><tr><th>Cliente</th><th className="text-right">Kg</th><th className="text-right">Pezzi</th></tr></thead>
            <tbody>
              {d.per_cliente.map((c, i) => (
                <tr key={c.cliente_id || i}><td>{c.cliente_nome}</td><td className="text-right font-mono">{fmtK(c.kg)}</td><td className="text-right text-xs">{c.pezzi.toFixed(0)}</td></tr>
              ))}
            </tbody>
          </table></div>
        </div>
        <div className="kpi-card p-0 overflow-hidden">
          <div className="px-4 py-3 border-b"><h4 className="font-display font-bold">Top articoli (kg)</h4></div>
          <div className="overflow-x-auto"><table className="data-table">
            <thead><tr><th>Articolo</th><th className="text-right">Kg</th><th className="text-right">Pezzi</th></tr></thead>
            <tbody>
              {d.per_articolo.map((a, i) => (
                <tr key={a.articolo_id || i}><td><div className="text-xs font-mono">{a.codice}</div><div className="text-sm">{a.descrizione}</div></td><td className="text-right font-mono">{fmtK(a.kg)}</td><td className="text-right text-xs">{a.pezzi.toFixed(0)}</td></tr>
              ))}
            </tbody>
          </table></div>
        </div>
      </div>
    </div>
  );
}

// ============== COSTO PER KG ==============
function CostoKgView({ d }) {
  const pieData = Object.entries(d.per_categoria).map(([k, v]) => ({ name: k, value: v }));
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi label="Costi totali" value={fmtE(d.totale_costi)} />
        <Kpi label="Kg prodotti" value={fmtK(d.totale_kg)} color="text-celeste" />
        <Kpi label="Costo medio €/kg" value={d.costo_kg_medio !== null ? `€ ${d.costo_kg_medio.toFixed(4)}` : "—"} color="text-amber-600" />
        <Kpi label="Anno" value={d.anno || "—"} color="text-slate-900" />
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="kpi-card p-4">
          <h4 className="font-display font-bold mb-3">Ripartizione costi per categoria</h4>
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="name" outerRadius={80} label={(e) => `${e.name}: ${fmtE(e.value)}`}>
                {pieData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip formatter={fmtE} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="kpi-card p-4">
          <h4 className="font-display font-bold mb-3">Costo per kg nel tempo</h4>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={d.per_mese}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="mese" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v, n) => n === "costo_kg" ? (v !== null ? `€ ${v.toFixed(4)}` : "—") : n === "kg" ? fmtK(v) : fmtE(v)} />
              <Line type="monotone" dataKey="costo_kg" stroke="#f59e0b" strokeWidth={2} name="Costo €/kg" />
              <Legend wrapperStyle={{ fontSize: 12 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="kpi-card p-0 overflow-hidden">
        <div className="px-4 py-3 border-b"><h4 className="font-display font-bold">Dettaglio mensile</h4></div>
        <div className="overflow-x-auto"><table className="data-table">
          <thead><tr><th>Mese</th><th className="text-right">Costi</th><th className="text-right">Kg prodotti</th><th className="text-right">€ / kg</th></tr></thead>
          <tbody>
            {d.per_mese.map(m => (
              <tr key={m.mese}><td className="font-mono">{m.mese}</td><td className="text-right font-mono">{fmtE(m.costi)}</td><td className="text-right font-mono">{fmtK(m.kg)}</td><td className="text-right font-mono font-bold">{m.costo_kg !== null ? `€ ${m.costo_kg.toFixed(4)}` : "—"}</td></tr>
            ))}
          </tbody>
        </table></div>
      </div>
    </div>
  );
}

// ============== MARGINALITA ==============
function MarginalitaView({ d }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Kpi label="Fatturato" value={fmtE(d.totale_fatturato)} />
        <Kpi label="Costi allocati" value={fmtE(d.totale_costi)} color="text-red-600" />
        <Kpi label="Kg totali" value={fmtK(d.totale_kg)} color="text-celeste" />
        <Kpi label="€ / kg medio" value={`€ ${(d.costo_kg_medio || 0).toFixed(4)}`} color="text-amber-600" />
        <Kpi label="Margine totale" value={fmtE(d.margine_totale)} color={d.margine_totale >= 0 ? "text-emerald-600" : "text-red-600"} />
      </div>

      <div className="kpi-card p-0 overflow-hidden">
        <div className="px-4 py-3 border-b"><h4 className="font-display font-bold">Marginalità per cliente</h4></div>
        <div className="overflow-x-auto"><table className="data-table">
          <thead><tr>
            <th>#</th><th>Cliente</th><th className="text-right">Fatturato</th><th className="text-right">Kg</th>
            <th className="text-right">Costo alloc.</th><th className="text-right">Margine €</th><th className="text-right">Margine %</th>
          </tr></thead>
          <tbody>
            {d.per_cliente.map((r, i) => (
              <tr key={r.cliente_id || i} data-testid={`marg-row-${i}`}>
                <td className="text-xs text-slate-400">{i + 1}</td>
                <td>{r.cliente_nome}</td>
                <td className="text-right font-mono">{fmtE(r.fatturato)}</td>
                <td className="text-right font-mono text-xs">{fmtK(r.kg)}</td>
                <td className="text-right font-mono text-xs text-red-600">{fmtE(r.costo_allocato)}</td>
                <td className={`text-right font-mono font-bold ${r.margine >= 0 ? "text-emerald-600" : "text-red-600"}`}>{fmtE(r.margine)}</td>
                <td className={`text-right font-mono ${r.margine >= 0 ? "text-emerald-600" : "text-red-600"}`}>{r.margine_perc !== null ? `${r.margine_perc.toFixed(1)}%` : "—"}</td>
              </tr>
            ))}
            {d.per_cliente.length === 0 && <tr><td colSpan={7} className="text-center py-8 text-slate-400">Nessun dato</td></tr>}
          </tbody>
        </table></div>
      </div>
    </div>
  );
}

// ============== AGING ==============
function AgingView({ d }) {
  const colors = { "0-30": "#10b981", "31-60": "#f59e0b", "61-90": "#ef4444", ">90": "#7f1d1d" };
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Kpi label="Totale sospeso" value={fmtE(d.totale_sospeso)} color="text-red-600" />
        {d.buckets.map(b => (
          <Kpi key={b.bucket} label={`${b.bucket} gg`} value={fmtE(b.totale)} sub={`${b.n} fatture`} color="" />
        ))}
      </div>

      <div className="kpi-card p-4">
        <h4 className="font-display font-bold mb-3">Distribuzione per anzianità</h4>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={d.buckets}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="bucket" />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip formatter={fmtE} />
            <Bar dataKey="totale">
              {d.buckets.map((b, i) => <Cell key={i} fill={colors[b.bucket]} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="kpi-card p-0 overflow-hidden">
        <div className="px-4 py-3 border-b flex justify-between items-center">
          <h4 className="font-display font-bold">Dettaglio fatture in sospeso</h4>
          <span className="text-xs text-slate-400 font-mono">oggi: {d.oggi}</span>
        </div>
        <div className="overflow-x-auto"><table className="data-table">
          <thead><tr><th>Numero</th><th>Cliente</th><th>Data emissione</th><th className="text-right">Giorni</th><th className="text-right">Totale</th><th>Bucket</th></tr></thead>
          <tbody>
            {d.dettagli.map(f => (
              <tr key={f.numero} data-testid={`aging-${f.numero}`}>
                <td className="font-mono text-xs">{f.numero}</td>
                <td>{f.cliente_nome}</td>
                <td className="text-xs font-mono">{(f.data || "").slice(0, 10)}</td>
                <td className="text-right font-mono">{f.giorni}</td>
                <td className="text-right font-mono font-bold">{fmtE(f.totale)}</td>
                <td><span className="px-2 py-0.5 rounded-full text-xs" style={{ backgroundColor: colors[f.bucket] + "22", color: colors[f.bucket] }}>{f.bucket} gg</span></td>
              </tr>
            ))}
            {d.dettagli.length === 0 && <tr><td colSpan={6} className="text-center py-8 text-slate-400">Nessun sospeso — perfetto!</td></tr>}
          </tbody>
        </table></div>
      </div>
    </div>
  );
}

// ============== KM AUTOMEZZI ==============
function KmView({ d }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <Kpi label="Km totali" value={`${(d.totale_km || 0).toFixed(0)} km`} color="text-celeste" />
        <Kpi label="Spesa totale" value={fmtE(d.totale_spesa)} color="text-amber-600" />
        <Kpi label="€ / km medio" value={d.totale_km > 0 ? `€ ${(d.totale_spesa / d.totale_km).toFixed(3)}` : "—"} />
      </div>

      <div className="kpi-card p-4">
        <h4 className="font-display font-bold mb-3">Andamento mensile</h4>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={d.per_mese}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="mese" tick={{ fontSize: 11 }} />
            <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v, n) => n === "spesa" ? fmtE(v) : `${v.toFixed(0)} km`} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar yAxisId="left" dataKey="km" fill="#0ea5e9" name="Km" />
            <Bar yAxisId="right" dataKey="spesa" fill="#f59e0b" name="Spesa €" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="kpi-card p-0 overflow-hidden">
        <div className="px-4 py-3 border-b"><h4 className="font-display font-bold">Dettaglio per automezzo</h4></div>
        <div className="overflow-x-auto"><table className="data-table">
          <thead><tr><th>Targa</th><th className="text-right">Km</th><th className="text-right">Spesa</th><th className="text-right">€ / km</th><th>Breakdown tipo</th></tr></thead>
          <tbody>
            {d.per_targa.map((t, i) => (
              <tr key={t.targa} data-testid={`km-targa-${i}`}>
                <td className="font-mono font-bold">{t.targa}</td>
                <td className="text-right font-mono">{t.km_totali.toFixed(0)} km</td>
                <td className="text-right font-mono">{fmtE(t.spesa_totale)}</td>
                <td className="text-right font-mono font-bold text-amber-600">{t.costo_km !== null ? `€ ${t.costo_km.toFixed(3)}` : "—"}</td>
                <td className="text-xs">{Object.entries(t.per_tipo).map(([k, v]) => <span key={k} className="inline-block mr-2"><span className="text-slate-400">{k}:</span> {fmtE(v)}</span>)}</td>
              </tr>
            ))}
            {d.per_targa.length === 0 && <tr><td colSpan={5} className="text-center py-8 text-slate-400">Nessun automezzo registrato</td></tr>}
          </tbody>
        </table></div>
      </div>
    </div>
  );
}
