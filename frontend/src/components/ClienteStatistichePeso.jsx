/**
 * Sezione "Statistiche peso" da mostrare nella scheda cliente (§12).
 * Filtri: anno, mese, intervallo date, categoria, articolo.
 * KPI: peso mese/anno/complessivo, ripartizione categoria peso, N° DDT, peso medio per DDT.
 */
import React, { useEffect, useState } from "react";
import api from "../lib/api";
import { Label } from "./ui/label";
import { Input } from "./ui/input";
import { Scales } from "@phosphor-icons/react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from "recharts";

const fmtKg = (v) => (Number(v) || 0).toLocaleString("it-IT", { minimumFractionDigits: 3, maximumFractionDigits: 3 }) + " kg";

const MESI = ["Gen","Feb","Mar","Apr","Mag","Giu","Lug","Ago","Set","Ott","Nov","Dic"];

export default function ClienteStatistichePeso({ clienteId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [articoli, setArticoli] = useState([]);
  const [filters, setFilters] = useState({
    anno: new Date().getFullYear(),
    mese: "",
    data_inizio: "",
    data_fine: "",
    categoria: "",
    articolo_id: "",
    use_range: false,
  });

  useEffect(() => {
    api.get("/articoli").then(r => setArticoli(r.data || [])).catch(() => {});
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const params = new URLSearchParams();
        if (filters.use_range) {
          if (filters.data_inizio) params.set("data_inizio", filters.data_inizio);
          if (filters.data_fine) params.set("data_fine", filters.data_fine);
        } else {
          if (filters.anno) params.set("anno", String(filters.anno));
          if (filters.mese) params.set("mese", String(filters.mese));
        }
        if (filters.categoria) params.set("categoria", filters.categoria);
        if (filters.articolo_id) params.set("articolo_id", filters.articolo_id);
        const { data: d } = await api.get(`/clienti/${clienteId}/statistiche-peso?${params.toString()}`);
        if (!cancelled) setData(d);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    if (clienteId) load();
    return () => { cancelled = true; };
  }, [clienteId, filters]);

  const cat = data?.periodo?.per_categoria_peso || [];
  const fromCat = (key) => (cat.find(c => c.categoria_peso === key)?.kg) || 0;
  const catAnno = data?.anno_corrente?.per_categoria_peso || [];
  const fromCatAnno = (key) => (catAnno.find(c => c.categoria_peso === key)?.kg) || 0;

  return (
    <div className="mb-4 p-3 rounded-lg border border-emerald-100 bg-emerald-50/40" data-testid="cliente-statistiche-peso">
      <div className="flex items-center gap-2 mb-2">
        <Scales size={16} className="text-emerald-600" weight="duotone" />
        <h4 className="font-display font-bold text-sm">Statistiche peso</h4>
        {loading && <span className="text-xs text-slate-400 ml-2">Caricamento…</span>}
      </div>

      {/* Filtri */}
      <div className="flex flex-wrap items-end gap-2 mb-3 text-xs">
        <div className="flex gap-1">
          <button onClick={() => setFilters(f => ({ ...f, use_range: false }))}
            className={`px-2 py-1 rounded ${!filters.use_range ? "bg-indaco text-white" : "bg-white border border-slate-200"}`}
            data-testid="cli-peso-mode-anno">
            Anno/Mese
          </button>
          <button onClick={() => setFilters(f => ({ ...f, use_range: true }))}
            className={`px-2 py-1 rounded ${filters.use_range ? "bg-indaco text-white" : "bg-white border border-slate-200"}`}
            data-testid="cli-peso-mode-range">
            Intervallo
          </button>
        </div>
        {!filters.use_range && (
          <>
            <div>
              <Label className="text-[10px] uppercase tracking-wide text-slate-500">Anno</Label>
              <Input type="number" className="h-8 w-24" value={filters.anno} onChange={e => setFilters(f => ({ ...f, anno: parseInt(e.target.value) || "" }))} data-testid="cli-peso-anno" />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wide text-slate-500">Mese</Label>
              <select className="h-8 px-1 border border-slate-200 rounded text-xs" value={filters.mese} onChange={e => setFilters(f => ({ ...f, mese: e.target.value }))} data-testid="cli-peso-mese">
                <option value="">Tutto l&apos;anno</option>
                {[1,2,3,4,5,6,7,8,9,10,11,12].map(m => <option key={m} value={m}>{MESI[m-1]}</option>)}
              </select>
            </div>
          </>
        )}
        {filters.use_range && (
          <>
            <div>
              <Label className="text-[10px] uppercase tracking-wide text-slate-500">Data dal</Label>
              <Input type="date" className="h-8 w-36" value={filters.data_inizio} onChange={e => setFilters(f => ({ ...f, data_inizio: e.target.value }))} />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wide text-slate-500">Data al</Label>
              <Input type="date" className="h-8 w-36" value={filters.data_fine} onChange={e => setFilters(f => ({ ...f, data_fine: e.target.value }))} />
            </div>
          </>
        )}
        <div>
          <Label className="text-[10px] uppercase tracking-wide text-slate-500">Articolo</Label>
          <select className="h-8 px-1 border border-slate-200 rounded text-xs w-48" value={filters.articolo_id} onChange={e => setFilters(f => ({ ...f, articolo_id: e.target.value }))} data-testid="cli-peso-articolo">
            <option value="">Tutti</option>
            {articoli.map(a => <option key={a.id} value={a.id}>{a.codice} — {a.descrizione}</option>)}
          </select>
        </div>
      </div>

      {/* KPI */}
      {data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2 text-xs">
            <div className="bg-white p-2 rounded border border-slate-200">
              <div className="text-[10px] uppercase text-slate-500">Periodo</div>
              <div className="font-mono font-bold text-emerald-700" data-testid="cli-peso-periodo-kg">{fmtKg(data.periodo.totale_kg)}</div>
              <div className="text-[10px] text-slate-500">{data.periodo.ddt_count} DDT · {data.periodo.totale_pezzi.toFixed(0)} pz</div>
            </div>
            <div className="bg-white p-2 rounded border border-slate-200">
              <div className="text-[10px] uppercase text-slate-500">Media/DDT</div>
              <div className="font-mono font-bold">{fmtKg(data.periodo.peso_medio_per_ddt)}</div>
              <div className="text-[10px] text-slate-500">g.: {fmtKg(data.periodo.peso_medio_giornaliero)}</div>
            </div>
            <div className="bg-white p-2 rounded border border-sky-200 border-l-4">
              <div className="text-[10px] uppercase text-sky-700">Biancheria</div>
              <div className="font-mono font-bold text-sky-700">{fmtKg(fromCat("BIANCHERIA_PIANA"))}</div>
            </div>
            <div className="bg-white p-2 rounded border border-emerald-200 border-l-4">
              <div className="text-[10px] uppercase text-emerald-700">Spugna</div>
              <div className="font-mono font-bold text-emerald-700">{fmtKg(fromCat("SPUGNA"))}</div>
            </div>
            <div className="bg-white p-2 rounded border border-violet-200 border-l-4">
              <div className="text-[10px] uppercase text-violet-700">Varie</div>
              <div className="font-mono font-bold text-violet-700">{fmtKg(fromCat("VARIE"))}</div>
            </div>
            <div className="bg-white p-2 rounded border border-slate-200">
              <div className="text-[10px] uppercase text-slate-500">Complessivo</div>
              <div className="font-mono font-bold text-indaco">{fmtKg(data.complessivo.totale_kg)}</div>
              <div className="text-[10px] text-slate-500">{data.complessivo.ddt_count} DDT tot.</div>
            </div>
          </div>

          {/* Mese e anno correnti */}
          <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] text-slate-600">
            <div className="bg-white p-2 rounded border border-slate-100">
              <b className="text-slate-800">Mese corrente:</b> {fmtKg(data.mese_corrente.totale_kg)} · {data.mese_corrente.ddt_count} DDT
            </div>
            <div className="bg-white p-2 rounded border border-slate-100">
              <b className="text-slate-800">Anno {new Date().getFullYear()}:</b> {fmtKg(data.anno_corrente.totale_kg)} · Bianch.: {fromCatAnno("BIANCHERIA_PIANA").toFixed(2)} · Spugna: {fromCatAnno("SPUGNA").toFixed(2)} · Varie: {fromCatAnno("VARIE").toFixed(2)}
            </div>
          </div>

          {/* Andamento mensile */}
          {Array.isArray(data.periodo.per_mese) && data.periodo.per_mese.length > 0 && (
            <div className="mt-3 bg-white p-2 rounded border border-slate-100" data-testid="cli-peso-chart">
              <div className="text-[10px] uppercase text-slate-500 mb-1">Andamento mensile kg</div>
              <ResponsiveContainer width="100%" height={140}>
                <BarChart data={data.periodo.per_mese}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="mese" fontSize={9} />
                  <YAxis fontSize={9} />
                  <Tooltip formatter={(v) => [`${Number(v).toFixed(3)} kg`, "kg"]} contentStyle={{ fontSize: 11 }} />
                  <Legend wrapperStyle={{ fontSize: 10 }} />
                  <Bar dataKey="kg" fill="#10b981" name="kg" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}
    </div>
  );
}
