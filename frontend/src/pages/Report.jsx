import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import ErrorBoundary from "../components/ErrorBoundary";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { ChartBar, CurrencyEur, Scales, Gauge, Clock, Truck, TrendUp, FileArrowDown, Archive, UploadSimple, FloppyDisk, Trash, MagnifyingGlass } from "@phosphor-icons/react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { toast } from "sonner";
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
  { v: "storico", l: "Storico (pre-app)", icon: Archive },
];

export default function Report() {
  const [tab, setTab] = useState("fatturato");
  const [anno, setAnno] = useState(new Date().getFullYear());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  // Filtri avanzati produzione (kg)
  const [prodFilters, setProdFilters] = useState({
    data_inizio: "",
    data_fine: "",
    cliente_id: "",
    categoria: "",
    use_range: false,   // se true, usa range date invece di anno
  });
  const [clienti, setClienti] = useState([]);
  const [articoloCategorie, setArticoloCategorie] = useState([]);
  const [articoliCheck, setArticoliCheck] = useState(null);

  useEffect(() => {
    if (tab !== "produzione") return;
    // Carica clienti + categorie articoli
    Promise.all([
      api.get("/clienti").catch(() => ({ data: [] })),
      api.get("/articoli").catch(() => ({ data: [] })),
      api.get("/reports/produzione/articoli-check").catch(() => ({ data: null })),
    ]).then(([c, a, ck]) => {
      setClienti(c.data || []);
      const cats = Array.from(new Set((a.data || []).map(x => x.categoria).filter(Boolean))).sort();
      setArticoloCategorie(cats);
      setArticoliCheck(ck.data);
    });
  }, [tab]);

  const buildProduzioneQuery = () => {
    const params = new URLSearchParams();
    if (prodFilters.use_range) {
      if (prodFilters.data_inizio) params.set("data_inizio", prodFilters.data_inizio);
      if (prodFilters.data_fine) params.set("data_fine", prodFilters.data_fine);
    } else {
      params.set("anno", String(anno));
    }
    if (prodFilters.cliente_id) params.set("cliente_id", prodFilters.cliente_id);
    if (prodFilters.categoria) params.set("categoria", prodFilters.categoria);
    return params.toString();
  };

  const fetchReport = async () => {
    if (tab === "storico") { setLoading(false); return; }
    setLoading(true); setData(null);
    try {
      const path = tab === "aging" ? "/reports/aging-sospesi" :
                   tab === "km" ? `/reports/km-automezzi?anno=${anno}` :
                   tab === "costo_kg" ? `/reports/costo-kg?anno=${anno}` :
                   tab === "fatturato" ? `/reports/fatturato?anno=${anno}` :
                   tab === "produzione" ? `/reports/produzione?${buildProduzioneQuery()}` :
                   `/reports/marginalita?anno=${anno}`;
      const { data: d } = await api.get(path);
      setData(d);
    } finally { setLoading(false); }
  };
  useEffect(() => { fetchReport(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [tab, anno, prodFilters]);

  return (
    <div>
      <PageHeader
        eyebrow="Business Intelligence"
        title="Report & Statistiche"
        subtitle="Fatturato, produzione, costi, marginalità e aging aggregati per mese, cliente, articolo e automezzo."
        actions={
          <div className="flex gap-2 items-center">
            {tab !== "storico" && (
              <button
                onClick={async () => {
                  try {
                    const res = await api.get(`/reports/${tab}/pdf?anno=${anno}`, { responseType: "blob" });
                    const url = URL.createObjectURL(res.data);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = `report-${tab}-${anno}.pdf`;
                    a.click();
                    URL.revokeObjectURL(url);
                  } catch { /* ignore */ }
                }}
                className="px-3 py-2 text-sm rounded-md border border-slate-200 hover:border-indaco hover:text-indaco flex items-center gap-2"
                data-testid="download-report-pdf">
                <FileArrowDown size={16} /> Scarica PDF
              </button>
            )}
            <Select value={String(anno)} onValueChange={v => { setData(null); setAnno(Number(v)); }}>
              <SelectTrigger className="w-28" data-testid="report-anno"><SelectValue /></SelectTrigger>
              <SelectContent>
                {[anno - 2, anno - 1, anno, anno + 1].map(y => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        }
      />

      <div className="flex gap-1 border-b border-slate-200 mb-6 overflow-x-auto">
        {TABS.map(t => {
          const Icon = t.icon;
          return (
            <button key={t.v} onClick={() => { setData(null); setTab(t.v); }}
              className={`px-4 py-2 text-sm font-medium whitespace-nowrap flex items-center gap-2 border-b-2 transition ${tab === t.v ? "border-indaco text-indaco" : "border-transparent text-slate-500 hover:text-slate-700"}`}
              data-testid={`report-tab-${t.v}`}>
              <Icon size={16} />{t.l}
            </button>
          );
        })}
      </div>

      {loading && <div className="kpi-card p-8 text-center text-slate-400">Caricamento…</div>}

      <ErrorBoundary resetKeys={[tab, anno]}>
        {!loading && data && tab === "fatturato" && <FatturatoView d={data} />}
        {!loading && data && tab === "produzione" && (
          <ProduzioneView
            d={data}
            filters={prodFilters}
            setFilters={setProdFilters}
            clienti={clienti}
            categorie={articoloCategorie}
            articoliCheck={articoliCheck}
            anno={anno}
            buildQuery={buildProduzioneQuery}
          />
        )}
        {!loading && data && tab === "costo_kg" && <CostoKgView d={data} />}
        {!loading && data && tab === "marginalita" && <MarginalitaView d={data} />}
        {!loading && data && tab === "aging" && <AgingView d={data} />}
        {!loading && data && tab === "km" && <KmView d={data} />}
        {tab === "storico" && <StoricoView anno={anno} />}
      </ErrorBoundary>
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
          <BarChart data={d.per_mese || []}>
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
            {(d.per_cliente || []).map((c, i) => (
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
function ProduzioneView({ d, filters, setFilters, clienti, categorie, articoliCheck, anno, buildQuery }) {
  const downloadXlsx = async () => {
    try {
      const res = await api.get(`/reports/produzione/xlsx?${buildQuery()}`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      const period = filters.use_range ? `${filters.data_inizio}_${filters.data_fine}` : String(anno);
      a.download = `Analisi_kg_${period}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Excel scaricato");
    } catch (e) {
      toast.error("Errore export Excel");
    }
  };
  return (
    <div className="space-y-6">
      {/* Filtri avanzati produzione */}
      <div className="kpi-card p-4">
        <div className="flex flex-wrap items-end gap-3">
          {/* Modalità periodo */}
          <div>
            <Label className="text-[11px] uppercase tracking-wide text-slate-500">Periodo</Label>
            <div className="flex gap-1 mt-1">
              <button
                onClick={() => setFilters(f => ({ ...f, use_range: false }))}
                className={`px-3 py-1.5 text-xs font-semibold rounded-md ${!filters.use_range ? "bg-indaco text-white" : "bg-white border border-slate-200 text-slate-600"}`}
                data-testid="prod-mode-anno"
              >Per anno</button>
              <button
                onClick={() => setFilters(f => ({ ...f, use_range: true }))}
                className={`px-3 py-1.5 text-xs font-semibold rounded-md ${filters.use_range ? "bg-indaco text-white" : "bg-white border border-slate-200 text-slate-600"}`}
                data-testid="prod-mode-range"
              >Intervallo date</button>
            </div>
          </div>
          {filters.use_range && (
            <>
              <div>
                <Label className="text-[11px] uppercase tracking-wide text-slate-500">Data dal</Label>
                <Input type="date" value={filters.data_inizio} onChange={e => setFilters(f => ({ ...f, data_inizio: e.target.value }))} className="h-9 w-40" data-testid="prod-data-inizio" />
              </div>
              <div>
                <Label className="text-[11px] uppercase tracking-wide text-slate-500">Data al</Label>
                <Input type="date" value={filters.data_fine} onChange={e => setFilters(f => ({ ...f, data_fine: e.target.value }))} className="h-9 w-40" data-testid="prod-data-fine" />
              </div>
            </>
          )}
          <div className="min-w-[220px] flex-1">
            <Label className="text-[11px] uppercase tracking-wide text-slate-500">Cliente</Label>
            <select
              value={filters.cliente_id}
              onChange={e => setFilters(f => ({ ...f, cliente_id: e.target.value }))}
              className="h-9 px-2 border border-slate-200 rounded-md text-sm w-full"
              data-testid="prod-cliente"
            >
              <option value="">Tutti i clienti</option>
              {clienti.map(c => (
                <option key={c.id} value={c.id}>
                  {c.denominazione_struttura || c.ragione_sociale || c.id}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label className="text-[11px] uppercase tracking-wide text-slate-500">Categoria</Label>
            <select
              value={filters.categoria}
              onChange={e => setFilters(f => ({ ...f, categoria: e.target.value }))}
              className="h-9 px-2 border border-slate-200 rounded-md text-sm w-40"
              data-testid="prod-categoria"
            >
              <option value="">Tutte</option>
              {categorie.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="ml-auto flex gap-2">
            {(filters.cliente_id || filters.categoria || filters.use_range) && (
              <Button variant="outline" size="sm" onClick={() => setFilters(f => ({ ...f, cliente_id: "", categoria: "", use_range: false, data_inizio: "", data_fine: "" }))} data-testid="prod-reset">Azzera</Button>
            )}
            <Button className="bg-emerald-600 hover:bg-emerald-700" size="sm" onClick={downloadXlsx} data-testid="prod-xlsx">
              <FileArrowDown size={14} className="mr-1" /> Excel
            </Button>
          </div>
        </div>
      </div>

      {/* Warning articoli senza peso / non classificati */}
      {articoliCheck && (articoliCheck.senza_peso_count > 0 || (articoliCheck.non_classificati_count || 0) > 0 || articoliCheck.sospetti_grammi?.length > 0) && (
        <div className="kpi-card p-4 border-l-4 border-amber-400 bg-amber-50" data-testid="prod-articoli-check">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 text-amber-600 font-bold text-lg">!</div>
            <div className="flex-1">
              <div className="font-display font-bold text-amber-900 text-sm">Attenzione: dati Articoli da verificare</div>
              {(articoliCheck.non_classificati_count || 0) > 0 && (
                <div className="text-xs text-amber-800 mt-1">
                  <b>{articoliCheck.non_classificati_count}</b> articolo/i <b>non classificato/i per peso</b> — assegna la categoria (Biancheria piana / Spugna / Varie) nella sezione Articoli.
                  <details className="mt-1">
                    <summary className="cursor-pointer text-amber-700">Mostra elenco</summary>
                    <ul className="mt-1 ml-4 list-disc">
                      {(articoliCheck.non_classificati || []).slice(0, 20).map(a => (
                        <li key={a.id}><span className="font-mono">{a.codice}</span> — {a.descrizione}</li>
                      ))}
                    </ul>
                  </details>
                </div>
              )}
              {articoliCheck.senza_peso_count > 0 && (
                <div className="text-xs text-amber-800 mt-1">
                  <b>{articoliCheck.senza_peso_count}</b> articolo/i senza <b>peso medio</b> impostato — i loro pezzi non contribuiscono al calcolo dei kg.
                  <details className="mt-1">
                    <summary className="cursor-pointer text-amber-700">Mostra elenco</summary>
                    <ul className="mt-1 ml-4 list-disc">
                      {articoliCheck.senza_peso.slice(0, 20).map(a => (
                        <li key={a.id}><span className="font-mono">{a.codice}</span> — {a.descrizione} {a.categoria && <span className="text-slate-500">({a.categoria})</span>}</li>
                      ))}
                    </ul>
                  </details>
                </div>
              )}
              {articoliCheck.sospetti_grammi?.length > 0 && (
                <div className="text-xs text-amber-800 mt-1">
                  {articoliCheck.sospetti_grammi.length} articolo/i con peso &ge; 50 kg (potrebbe essere dato in grammi, verifica).
                </div>
              )}
              <div className="text-[11px] text-slate-500 mt-1 italic">
                {articoliCheck.note} — unità standard: {articoliCheck.unita}.
              </div>
            </div>
          </div>
        </div>
      )}

      {/* KPI principali */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi label="Totale kg prodotti" value={fmtK(d.totale_kg)} sub={d.data_inizio ? `${d.data_inizio} → ${d.data_fine}` : `anno ${d.anno || "—"}`} />
        <Kpi label="Totale pezzi" value={(d.totale_pezzi || 0).toFixed(0)} color="text-slate-900" />
        <Kpi label="Peso medio" value={d.totale_pezzi ? `${(d.totale_kg / d.totale_pezzi).toFixed(2)} kg/pz` : "—"} color="text-celeste" />
        <Kpi label="N° DDT" value={d.ddt_count || 0} color="text-amber-600" />
      </div>

      {/* Grafico mensile */}
      <div className="kpi-card p-4">
        <h4 className="font-display font-bold mb-3">Andamento kg per mese</h4>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={d.per_mese || []}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="mese" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v, n) => n === "kg" ? fmtK(v) : v} />
            <Line type="monotone" dataKey="kg" stroke="#4f46e5" strokeWidth={2} dot={{ r: 4 }} name="kg" />
            <Line type="monotone" dataKey="pezzi" stroke="#0ea5e9" strokeDasharray="4 4" name="pezzi" />
            <Legend wrapperStyle={{ fontSize: 12 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Per categoria peso (biancheria piana / spugna / varie / non classificato) */}
      <div className="kpi-card p-0 overflow-hidden" data-testid="prod-tab-catpeso">
        <div className="px-4 py-3 border-b flex items-center justify-between">
          <h4 className="font-display font-bold">Per categoria peso (biancheria piana / spugna / varie)</h4>
          <span className="text-[11px] text-slate-500 italic">Somma coerente con il totale DDT</span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-0 border-t">
          {(d.per_categoria_peso || []).map((c) => {
            const perc = d.totale_kg ? (c.kg / d.totale_kg * 100) : 0;
            const color = c.categoria_peso === "BIANCHERIA_PIANA" ? "bg-sky-50 text-sky-800 border-sky-200" :
                          c.categoria_peso === "SPUGNA" ? "bg-emerald-50 text-emerald-800 border-emerald-200" :
                          c.categoria_peso === "VARIE" ? "bg-violet-50 text-violet-800 border-violet-200" :
                          "bg-amber-50 text-amber-800 border-amber-300";
            return (
              <div key={c.categoria_peso} className={`p-4 border-r last:border-r-0 border-b md:border-b-0 ${color}`}>
                <div className="text-[11px] uppercase font-semibold tracking-wide opacity-80">{c.label}</div>
                <div className="text-2xl font-display font-bold mt-1">{fmtK(c.kg)}</div>
                <div className="text-xs opacity-70 mt-1">{(c.pezzi || 0).toFixed(0)} pz · {perc.toFixed(1)}%</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Per categoria + Per anno */}
      <div className="grid md:grid-cols-2 gap-4">
        <div className="kpi-card p-0 overflow-hidden">
          <div className="px-4 py-3 border-b"><h4 className="font-display font-bold">Per categoria articolo</h4></div>
          <div className="overflow-x-auto"><table className="data-table" data-testid="prod-tab-categoria">
            <thead><tr><th>Categoria</th><th className="text-right">Kg</th><th className="text-right">Pezzi</th><th className="text-right">Articoli</th></tr></thead>
            <tbody>
              {(d.per_categoria || []).map((c, i) => (
                <tr key={c.categoria || i}>
                  <td>{c.categoria || "—"}</td>
                  <td className="text-right font-mono font-bold">{fmtK(c.kg)}</td>
                  <td className="text-right text-xs">{(c.pezzi || 0).toFixed(0)}</td>
                  <td className="text-right text-xs">{c.articoli || 0}</td>
                </tr>
              ))}
              {(d.per_categoria || []).length === 0 && <tr><td colSpan={4} className="text-center py-6 text-slate-400">Nessun dato</td></tr>}
            </tbody>
          </table></div>
        </div>
        <div className="kpi-card p-0 overflow-hidden">
          <div className="px-4 py-3 border-b"><h4 className="font-display font-bold">Per anno</h4></div>
          <div className="overflow-x-auto"><table className="data-table" data-testid="prod-tab-anno">
            <thead><tr><th>Anno</th><th className="text-right">Kg</th><th className="text-right">Pezzi</th></tr></thead>
            <tbody>
              {(d.per_anno || []).map((y, i) => (
                <tr key={y.anno || i}>
                  <td className="font-semibold">{y.anno}</td>
                  <td className="text-right font-mono">{fmtK(y.kg)}</td>
                  <td className="text-right text-xs">{(y.pezzi || 0).toFixed(0)}</td>
                </tr>
              ))}
              {(d.per_anno || []).length === 0 && <tr><td colSpan={3} className="text-center py-6 text-slate-400">Nessun dato</td></tr>}
            </tbody>
          </table></div>
        </div>
      </div>

      {/* Per cliente + Per articolo */}
      <div className="grid md:grid-cols-2 gap-4">
        <div className="kpi-card p-0 overflow-hidden">
          <div className="px-4 py-3 border-b"><h4 className="font-display font-bold">Top clienti (kg)</h4></div>
          <div className="overflow-x-auto max-h-96"><table className="data-table" data-testid="prod-tab-cliente">
            <thead><tr><th>Cliente</th><th className="text-right">Kg</th><th className="text-right">Pezzi</th></tr></thead>
            <tbody>
              {(d.per_cliente || []).slice(0, 30).map((c, i) => (
                <tr key={c.cliente_id || i}><td>{c.cliente_nome}</td><td className="text-right font-mono">{fmtK(c.kg)}</td><td className="text-right text-xs">{(c.pezzi || 0).toFixed(0)}</td></tr>
              ))}
            </tbody>
          </table></div>
        </div>
        <div className="kpi-card p-0 overflow-hidden">
          <div className="px-4 py-3 border-b"><h4 className="font-display font-bold">Top articoli (kg)</h4></div>
          <div className="overflow-x-auto max-h-96"><table className="data-table" data-testid="prod-tab-articolo">
            <thead><tr><th>Articolo</th><th>Categoria</th><th className="text-right">Kg</th><th className="text-right">Pezzi</th></tr></thead>
            <tbody>
              {(d.per_articolo || []).slice(0, 30).map((a, i) => (
                <tr key={a.articolo_id || i}>
                  <td><div className="text-xs font-mono">{a.codice}</div><div className="text-sm">{a.descrizione}</div></td>
                  <td className="text-xs text-slate-500">{a.categoria || "—"}</td>
                  <td className="text-right font-mono">{fmtK(a.kg)}</td>
                  <td className="text-right text-xs">{(a.pezzi || 0).toFixed(0)}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </div>
      </div>

      {/* Per singolo DDT */}
      <div className="kpi-card p-0 overflow-hidden">
        <div className="px-4 py-3 border-b flex items-center justify-between">
          <h4 className="font-display font-bold">Dettaglio per singolo DDT</h4>
          <span className="text-xs text-slate-500">{d.ddt_count || 0} DDT (visualizzati {(d.per_ddt || []).length})</span>
        </div>
        <div className="overflow-x-auto max-h-[500px]"><table className="data-table" data-testid="prod-tab-ddt">
          <thead className="sticky top-0 bg-white">
            <tr>
              <th>Numero</th>
              <th>Data</th>
              <th>Cliente</th>
              <th className="text-right" title="Biancheria piana">Bianch.</th>
              <th className="text-right">Spugna</th>
              <th className="text-right">Varie</th>
              <th className="text-right" title="Non classificato">N.class.</th>
              <th className="text-right">Kg totali</th>
              <th className="text-right">Pezzi</th>
            </tr>
          </thead>
          <tbody>
            {(d.per_ddt || []).map((r) => (
              <tr key={r.ddt_id}>
                <td className="font-mono text-xs">{r.numero}</td>
                <td className="text-xs">{r.data ? new Date(r.data).toLocaleDateString("it-IT") : "—"}</td>
                <td>{r.cliente_nome}</td>
                <td className="text-right text-xs font-mono text-sky-700">{r.kg_biancheria_piana ? fmtK(r.kg_biancheria_piana) : "—"}</td>
                <td className="text-right text-xs font-mono text-emerald-700">{r.kg_spugna ? fmtK(r.kg_spugna) : "—"}</td>
                <td className="text-right text-xs font-mono text-violet-700">{r.kg_varie ? fmtK(r.kg_varie) : "—"}</td>
                <td className="text-right text-xs font-mono text-amber-700">{r.kg_non_classificato ? fmtK(r.kg_non_classificato) : "—"}</td>
                <td className="text-right font-mono font-bold">{fmtK(r.kg)}</td>
                <td className="text-right text-xs">{(r.pezzi || 0).toFixed(0)}</td>
              </tr>
            ))}
            {(d.per_ddt || []).length === 0 && <tr><td colSpan={9} className="text-center py-8 text-slate-400">Nessun DDT nel periodo</td></tr>}
          </tbody>
        </table></div>
      </div>
    </div>
  );
}

// ============== COSTO PER KG ==============
function CostoKgView({ d }) {
  const pieData = Object.entries(d.per_categoria || {})
    .map(([k, v]) => ({ name: k, value: Number(v?.totale ?? v ?? 0) }))
    .filter(e => e.value > 0);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi label="Costi totali" value={fmtE(d.totale_costi)} />
        <Kpi label="Kg prodotti" value={fmtK(d.totale_kg)} color="text-celeste" />
        <Kpi label="Costo medio €/kg" value={d.costo_kg_medio != null ? `€ ${Number(d.costo_kg_medio).toFixed(4)}` : "—"} color="text-amber-600" />
        <Kpi label="Anno" value={d.anno || "—"} color="text-slate-900" />
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="kpi-card p-4">
          <h4 className="font-display font-bold mb-3">Ripartizione costi per categoria</h4>
          {pieData.length === 0 ? (
            <div className="text-center py-10 text-slate-400 text-sm">Nessun costo registrato</div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" outerRadius={80} label={(e) => `${e.name}: ${fmtE(e.value)}`}>
                  {pieData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip formatter={(v) => fmtE(v)} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
        <div className="kpi-card p-4">
          <h4 className="font-display font-bold mb-3">Costo per kg nel tempo</h4>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={d.per_mese || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="mese" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v, n) => {
                if (v == null) return "—";
                if (n === "costo_kg") return `€ ${Number(v).toFixed(4)}`;
                if (n === "kg") return fmtK(v);
                return fmtE(v);
              }} />
              <Line type="monotone" dataKey="costo_kg" stroke="#f59e0b" strokeWidth={2} name="Costo €/kg" connectNulls />
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
            {(d.per_mese || []).map(m => (
              <tr key={m.mese}>
                <td className="font-mono">{m.mese}</td>
                <td className="text-right font-mono">{fmtE(m.costi)}</td>
                <td className="text-right font-mono">{fmtK(m.kg)}</td>
                <td className="text-right font-mono font-bold">{m.costo_kg != null ? `€ ${Number(m.costo_kg).toFixed(4)}` : "—"}</td>
              </tr>
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
            {(d.per_cliente || []).map((r, i) => (
              <tr key={r.cliente_id || i} data-testid={`marg-row-${i}`}>
                <td className="text-xs text-slate-400">{i + 1}</td>
                <td>{r.cliente_nome}</td>
                <td className="text-right font-mono">{fmtE(r.fatturato)}</td>
                <td className="text-right font-mono text-xs">{fmtK(r.kg)}</td>
                <td className="text-right font-mono text-xs text-red-600">{fmtE(r.costo_allocato)}</td>
                <td className={`text-right font-mono font-bold ${r.margine >= 0 ? "text-emerald-600" : "text-red-600"}`}>{fmtE(r.margine)}</td>
                <td className={`text-right font-mono ${r.margine >= 0 ? "text-emerald-600" : "text-red-600"}`}>{r.margine_perc != null ? `${Number(r.margine_perc).toFixed(1)}%` : "—"}</td>
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
        {(d.buckets || []).map(b => (
          <Kpi key={b.bucket} label={`${b.bucket} gg`} value={fmtE(b.totale)} sub={`${b.n} fatture`} color="" />
        ))}
      </div>

      <div className="kpi-card p-4">
        <h4 className="font-display font-bold mb-3">Distribuzione per anzianità</h4>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={d.buckets || []}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="bucket" />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip formatter={fmtE} />
            <Bar dataKey="totale">
              {(d.buckets || []).map((b, i) => <Cell key={i} fill={colors[b.bucket]} />)}
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
            {(d.dettagli || []).map(f => (
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
          <BarChart data={d.per_mese || []}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="mese" tick={{ fontSize: 11 }} />
            <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v, n) => {
              if (v == null) return "—";
              return n === "spesa" ? fmtE(v) : `${Number(v).toFixed(0)} km`;
            }} />
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
            {(d.per_targa || []).map((t, i) => (
              <tr key={t.targa} data-testid={`km-targa-${i}`}>
                <td className="font-mono font-bold">{t.targa}</td>
                <td className="text-right font-mono">{(t.km_totali || 0).toFixed(0)} km</td>
                <td className="text-right font-mono">{fmtE(t.spesa_totale)}</td>
                <td className="text-right font-mono font-bold text-amber-600">{t.costo_km != null ? `€ ${Number(t.costo_km).toFixed(3)}` : "—"}</td>
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


// ============== STORICO (PRE-APP) ==============
const MESI_LABELS = ["", "Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"];

function StoricoView({ anno }) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [annoSel, setAnnoSel] = useState(anno);
  const [importOpen, setImportOpen] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/fatturato-storico/summary?anno=${annoSel}`);
      setSummary(data);
    } catch (e) {
      toast.error("Errore caricamento storico");
    } finally { setLoading(false); }
  };
  useEffect(() => { fetchData(); }, [annoSel]);

  if (loading) return <div className="kpi-card p-8 text-center text-slate-400">Caricamento…</div>;

  const empty = !summary || summary.per_cliente.length === 0;
  const filtered = (summary?.per_cliente || []).filter(c =>
    !search || (c.cliente_denominazione || "").toLowerCase().includes(search.toLowerCase()) ||
    (c.cliente_ragione_sociale || "").toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="kpi-card p-4 flex flex-wrap gap-3 items-center justify-between">
        <div className="flex items-center gap-3">
          <Archive size={20} className="text-indaco" weight="duotone" />
          <div>
            <h3 className="font-display font-bold">Storico fatturato pre-app</h3>
            <p className="text-xs text-slate-500">Dati produzione importati da Excel (netto IVA, per cliente e mese).</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {(summary?.anni_disponibili || []).length > 0 && (
            <Select value={String(annoSel)} onValueChange={v => setAnnoSel(Number(v))}>
              <SelectTrigger className="w-28 h-9" data-testid="storico-anno"><SelectValue /></SelectTrigger>
              <SelectContent>
                {summary.anni_disponibili.map(y => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}
              </SelectContent>
            </Select>
          )}
          <Button onClick={() => setImportOpen(true)} className="bg-indaco hover:bg-indaco-dark" data-testid="storico-import-btn">
            <UploadSimple size={16} className="mr-1" />Importa Excel
          </Button>
        </div>
      </div>

      {empty ? (
        <div className="kpi-card p-12 text-center">
          <Archive size={48} className="mx-auto mb-3 text-slate-300" weight="duotone" />
          <h4 className="font-display font-bold text-lg mb-1">Nessun dato storico</h4>
          <p className="text-sm text-slate-500 mb-4">Importa il file Excel della contabilità per visualizzare lo storico per cliente e mese.</p>
          <Button onClick={() => setImportOpen(true)} className="bg-indaco hover:bg-indaco-dark">
            <UploadSimple size={16} className="mr-1" />Importa file Excel
          </Button>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <Kpi label="Totale storico" value={fmtE(summary.totale)} sub={`anno ${annoSel}`} />
            <Kpi label="Clienti" value={summary.per_cliente.length} color="text-slate-900" />
            <Kpi label="Mesi coperti" value={summary.per_mese.length} color="text-celeste" />
          </div>

          <div className="kpi-card p-4">
            <h4 className="font-display font-bold mb-3">Andamento mensile</h4>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={summary.per_mese}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="periodo" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip formatter={(v) => fmtE(v)} />
                <Bar dataKey="totale" fill="#4f46e5" name="Totale netto" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="kpi-card p-0 overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-200 flex items-center gap-3">
              <h4 className="font-display font-bold">Per cliente ({filtered.length})</h4>
              <div className="ml-auto relative">
                <MagnifyingGlass size={14} className="absolute left-2.5 top-2.5 text-slate-400" />
                <Input
                  placeholder="Cerca cliente…"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  className="pl-8 h-9 w-64"
                  data-testid="storico-search"
                />
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Cliente</th>
                    {[...Array(12)].map((_, i) => <th key={i} className="text-right">{MESI_LABELS[i + 1]}</th>)}
                    <th className="text-right">Totale</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(c => (
                    <tr key={c.cliente_id}>
                      <td>
                        <div className="font-medium">{c.cliente_denominazione || "—"}</div>
                        {c.cliente_ragione_sociale && c.cliente_ragione_sociale !== c.cliente_denominazione && (
                          <div className="text-xs text-slate-500">{c.cliente_ragione_sociale}</div>
                        )}
                      </td>
                      {[...Array(12)].map((_, i) => {
                        const key = `${annoSel}-${String(i + 1).padStart(2, "0")}`;
                        const v = c.per_mese[key];
                        return <td key={i} className={`text-right font-mono text-xs ${v ? "" : "text-slate-300"}`}>{v ? fmtE(v) : "—"}</td>;
                      })}
                      <td className="text-right font-mono font-bold text-indaco">{fmtE(c.totale)}</td>
                    </tr>
                  ))}
                  {filtered.length === 0 && <tr><td colSpan={14} className="text-center py-8 text-slate-400">Nessun risultato</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      <ImportStoricoDialog open={importOpen} onOpenChange={setImportOpen} onDone={fetchData} />
    </div>
  );
}

function ImportStoricoDialog({ open, onOpenChange, onDone }) {
  const [step, setStep] = useState(1);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [overrides, setOverrides] = useState({});

  const reset = () => { setStep(1); setFile(null); setPreview(null); setOverrides({}); };

  const handleClose = (o) => {
    onOpenChange(o);
    if (!o) setTimeout(reset, 300);
  };

  const upload = async () => {
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/imports/fatturato-storico/preview", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setPreview(data);
      const init = {};
      data.items.forEach(i => { if (i.cliente_id) init[i.struttura_excel] = i.cliente_id; });
      setOverrides(init);
      setStep(2);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore parsing file");
    } finally { setUploading(false); }
  };

  const commit = async () => {
    setCommitting(true);
    try {
      const items = preview.items.map(i => ({
        cliente_id: overrides[i.struttura_excel] || null,
        struttura_excel: i.struttura_excel,
        mese: i.mese,
        anno: i.anno,
        totale: i.totale,
      }));
      const { data } = await api.post("/imports/fatturato-storico/commit", { items });
      toast.success(`Importate ${data.upserted} righe · ${data.skipped} saltate`);
      onDone?.();
      handleClose(false);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore conferma");
    } finally { setCommitting(false); }
  };

  const strutture = preview ? (() => {
    const map = {};
    preview.items.forEach(i => {
      if (!map[i.struttura_excel]) {
        map[i.struttura_excel] = {
          struttura_excel: i.struttura_excel,
          match_score: i.match_score,
          match_reason: i.match_reason,
          righe: [],
        };
      }
      map[i.struttura_excel].righe.push(i);
    });
    return Object.values(map);
  })() : [];

  const totaleFinale = preview ? preview.items
    .filter(i => overrides[i.struttura_excel])
    .reduce((acc, i) => acc + i.totale, 0) : 0;
  const matchedCount = strutture.filter(s => overrides[s.struttura_excel]).length;

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-5xl max-h-[92vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <UploadSimple size={20} className="text-indaco" />
            Importa storico fatturato da Excel
          </DialogTitle>
        </DialogHeader>

        {step === 1 && (
          <div className="space-y-4">
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm">
              <p className="font-semibold text-amber-900 mb-1">Formato atteso:</p>
              <p className="text-amber-800 text-xs">
                File Excel con un foglio &quot;contabilità&quot;. Per ogni struttura una sezione con header (nome) e righe mensili:<br />
                <code className="font-mono text-[11px]">[A]=Nome struttura · [B]=Proforma Gennaio 26 · [D]=Importo netto IVA</code>
              </p>
            </div>
            <div>
              <Label>Seleziona file</Label>
              <Input type="file" accept=".xlsx,.xls"
                onChange={e => setFile(e.target.files?.[0] || null)}
                data-testid="storico-file-input" />
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-slate-200">
              <Button variant="outline" onClick={() => handleClose(false)}>Annulla</Button>
              <Button onClick={upload} disabled={!file || uploading} className="bg-indaco hover:bg-indaco-dark" data-testid="storico-upload-btn">
                {uploading ? "Analisi…" : "Analizza file"}
              </Button>
            </div>
          </div>
        )}

        {step === 2 && preview && (
          <div className="space-y-4">
            <div className="grid grid-cols-4 gap-3">
              <Kpi label="Righe" value={preview.summary.total_rows} />
              <Kpi label="Strutture" value={preview.summary.strutture_uniche} />
              <Kpi label="Matchate" value={matchedCount} color="text-emerald-600" />
              <Kpi label="Da abbinare" value={preview.summary.strutture_uniche - matchedCount} color="text-amber-600" />
            </div>

            <div className="text-xs text-slate-500">
              Verifica l&apos;abbinamento di ogni struttura. Le righe senza cliente abbinato saranno saltate.
            </div>

            <div className="border border-slate-200 rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                  <tr>
                    <th className="p-2 text-left">Struttura nel file</th>
                    <th className="p-2 text-left">Cliente abbinato</th>
                    <th className="p-2 text-right">Mesi</th>
                    <th className="p-2 text-right">Totale netto</th>
                  </tr>
                </thead>
                <tbody>
                  {strutture.map(s => {
                    const total = s.righe.reduce((a, r) => a + r.totale, 0);
                    const cli = overrides[s.struttura_excel];
                    return (
                      <tr key={s.struttura_excel} className="border-b border-slate-100">
                        <td className="p-2">
                          <div className="font-medium">{s.struttura_excel}</div>
                          {s.match_reason !== "esatto" && (
                            <div className="text-[10px] text-amber-600 font-mono">
                              {s.match_reason} · score {s.match_score}
                            </div>
                          )}
                        </td>
                        <td className="p-2">
                          <Select
                            value={cli || "__none__"}
                            onValueChange={v => setOverrides({ ...overrides, [s.struttura_excel]: v === "__none__" ? null : v })}>
                            <SelectTrigger className="h-8">
                              <SelectValue placeholder="Seleziona…" />
                            </SelectTrigger>
                            <SelectContent className="max-h-64">
                              <SelectItem value="__none__">— Salta —</SelectItem>
                              {preview.clienti.map(c => (
                                <SelectItem key={c.id} value={c.id}>{c.label}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </td>
                        <td className="p-2 text-right text-xs font-mono text-slate-500">
                          {s.righe.map(r => `${MESI_LABELS[r.mese]}${String(r.anno).slice(2)}`).join(", ")}
                        </td>
                        <td className="p-2 text-right font-mono font-bold text-indaco">{fmtE(total)}</td>
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot className="bg-indaco/5 border-t-2 border-indaco">
                  <tr>
                    <td colSpan={3} className="p-2 text-right font-semibold">Totale da importare ({matchedCount} strutture):</td>
                    <td className="text-right font-mono font-bold text-indaco">{fmtE(totaleFinale)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-200">
              <Button variant="outline" onClick={() => setStep(1)}>Indietro</Button>
              <Button onClick={commit} disabled={committing || matchedCount === 0}
                className="bg-emerald-600 hover:bg-emerald-700" data-testid="storico-commit-btn">
                <FloppyDisk size={14} className="mr-1" />
                {committing ? "Salvataggio…" : `Importa ${matchedCount} strutture`}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
