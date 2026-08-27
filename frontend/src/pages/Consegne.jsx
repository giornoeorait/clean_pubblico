import React, { useCallback, useEffect, useState } from "react";
import api, { formatApiErrorDetail as errMsg } from "../lib/api";
import { toast } from "sonner";
import { GiroMappa } from "../components/GiroMappa";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import {
  MapPin, Path, CaretLeft, CaretRight, NavigationArrow, Phone,
  Package, Clock, House, Warning, Truck, Printer,
} from "@phosphor-icons/react";

const todayISO = () => new Date().toLocaleDateString("sv-SE");
const fmtGiorno = (d) => new Date(d + "T12:00:00").toLocaleDateString("it-IT", { weekday: "long", day: "2-digit", month: "long", year: "numeric" });
const fmtMin = (m) => {
  if (m == null) return "—";
  if (m < 60) return `${Math.round(m)} min`;
  return `${Math.floor(m / 60)}h ${Math.round(m % 60)}m`;
};

export default function Consegne() {
  const [data, setData] = useState(todayISO());
  const [lista, setLista] = useState(null);
  const [giro, setGiro] = useState(null);
  const [loading, setLoading] = useState(false);
  const [calcolando, setCalcolando] = useState(false);

  const shiftDay = (n) => {
    const d = new Date(data + "T12:00:00");
    d.setDate(d.getDate() + n);
    setData(d.toLocaleDateString("sv-SE"));
  };

  const load = useCallback(async () => {
    setLoading(true);
    setGiro(null);
    try {
      const { data: res } = await api.get(`/consegne?data=${data}`);
      setLista(res);
    } catch (e) { toast.error(errMsg(e)); }
    setLoading(false);
  }, [data]);

  useEffect(() => { load(); }, [load]);

  const calcolaGiro = async () => {
    setCalcolando(true);
    try {
      const { data: res } = await api.post("/consegne/giro", { data });
      setGiro(res);
      if (res.tappe.length === 0 && res.senza_indirizzo.length === 0) toast.info("Nessuna consegna per questo giorno");
      else toast.success(`Giro calcolato: ${res.tappe.length} tappe, ${fmtMin(res.totale_min)}`);
    } catch (e) { toast.error(errMsg(e)); }
    setCalcolando(false);
  };

  const stampaGiro = async () => {
    try {
      const res = await api.get(`/consegne/giro/pdf?data=${data}`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      window.open(url, "_blank");
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) { toast.error(errMsg(e)); }
  };

  return (
    <div className="space-y-6" data-testid="consegne-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl md:text-3xl font-bold flex items-center gap-2"><Truck size={28} className="text-indaco" />Consegne</h1>
          <p className="text-sm text-slate-500 capitalize">{fmtGiorno(data)}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" onClick={() => shiftDay(-1)} data-testid="consegne-prev-day"><CaretLeft size={16} /></Button>
          <Input type="date" value={data} onChange={e => e.target.value && setData(e.target.value)} className="w-40" data-testid="consegne-date-input" />
          <Button variant="outline" size="icon" onClick={() => shiftDay(1)} data-testid="consegne-next-day"><CaretRight size={16} /></Button>
          <Button variant="outline" size="sm" onClick={() => setData(todayISO())} data-testid="consegne-today-btn">Oggi</Button>
        </div>
      </div>

      {/* Elenco consegne */}
      <div className="kpi-card p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-display font-bold text-sm flex items-center gap-2">
            <Package size={18} className="text-indaco" />Consegne del giorno {lista && <span className="text-slate-400 font-normal">({lista.n_consegne})</span>}
          </h3>
          {lista && lista.n_consegne > 0 && (
            <Button onClick={calcolaGiro} disabled={calcolando} size="sm" className="bg-indaco hover:bg-indaco/90" data-testid="calcola-giro-btn">
              <Path size={16} className="mr-1.5" />{calcolando ? "Calcolo in corso…" : "Calcola giro ottimale"}
            </Button>
          )}
        </div>
        {loading && <div className="text-sm text-slate-400 p-4">Caricamento…</div>}
        {!loading && lista && lista.consegne.length === 0 && (
          <div className="text-sm text-slate-400 p-6 text-center border-2 border-dashed border-slate-200 rounded-xl">Nessuna consegna prevista per questo giorno</div>
        )}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
          {!loading && (lista?.consegne || []).map(c => (
            <div key={c.cliente_id} className="border border-slate-200 rounded-xl p-3 hover:border-indaco/40 transition-colors" data-testid={`consegna-card-${c.cliente_id}`}>
              <div className="font-semibold text-sm">{c.cliente}</div>
              <div className="text-xs text-slate-500 flex items-start gap-1 mt-1"><MapPin size={14} className="flex-shrink-0 mt-0.5" />{c.indirizzo || <span className="text-red-500">indirizzo mancante</span>}</div>
              <div className="text-xs text-slate-500 mt-1.5 flex flex-wrap gap-x-3">
                {c.ordini.map(o => <span key={o.numero} className="font-mono">{o.numero} → {o.ddt_numero}</span>)}
              </div>
              <div className="text-xs font-mono text-indaco mt-1">{c.pezzi} pz</div>
            </div>
          ))}
        </div>
      </div>

      {/* Giro ottimizzato */}
      {giro && giro.tappe.length > 0 && (
        <div className="kpi-card p-4" data-testid="giro-panel">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <h3 className="font-display font-bold text-sm flex items-center gap-2"><Path size={18} className="text-emerald-600" />Giro suggerito (andata e ritorno)</h3>
            <div className="flex items-center gap-3">
              <span className="text-sm font-mono text-slate-600"><Clock size={14} className="inline mr-1" />{fmtMin(giro.totale_min)} · {giro.totale_km} km{giro.fonte_tempi === "stima" && <span className="text-amber-500 ml-1">(stima)</span>}</span>
              <a href={giro.gmaps_url} target="_blank" rel="noreferrer" data-testid="apri-gmaps-btn">
                <Button size="sm" className="bg-emerald-600 hover:bg-emerald-500"><NavigationArrow size={16} className="mr-1.5" />Apri navigazione</Button>
              </a>
              <Button size="sm" variant="outline" onClick={stampaGiro} data-testid="stampa-giro-btn">
                <Printer size={16} className="mr-1.5" />Stampa giro
              </Button>
            </div>
          </div>

          <div className="grid lg:grid-cols-2 gap-4">
            <div className="space-y-2">
              <div className="flex items-center gap-3 p-3 bg-slate-50 rounded-xl text-sm">
                <span className="w-8 h-8 rounded-full bg-slate-700 text-white flex items-center justify-center flex-shrink-0"><House size={16} /></span>
                <div><b>Partenza — Lavanderia</b><div className="text-xs text-slate-500">{giro.partenza.indirizzo}</div></div>
              </div>
              {giro.tappe.map(t => (
                <div key={t.posizione} className="flex items-center gap-3 p-3 border border-slate-200 rounded-xl text-sm" data-testid={`tappa-${t.posizione}`}>
                  <span className="w-8 h-8 rounded-full bg-indaco text-white font-bold flex items-center justify-center flex-shrink-0">{t.posizione}</span>
                  <div className="flex-1 min-w-0">
                    <b>{t.cliente}</b>
                    <div className="text-xs text-slate-500 truncate">{t.indirizzo}</div>
                    <div className="text-xs text-slate-400 font-mono">{t.ordini.map(o => o.ddt_numero).join(", ")} · {t.pezzi} pz{t.telefono && <a href={`tel:${t.telefono}`} className="ml-2 text-indaco"><Phone size={12} className="inline" /> {t.telefono}</a>}</div>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <div className="font-mono text-emerald-600 font-semibold">{fmtMin(t.tempo_tappa_min)}</div>
                    <div className="text-xs text-slate-400 font-mono">{t.km_tappa} km</div>
                  </div>
                </div>
              ))}
              <div className="flex items-center gap-3 p-3 bg-slate-50 rounded-xl text-sm">
                <span className="w-8 h-8 rounded-full bg-slate-700 text-white flex items-center justify-center flex-shrink-0"><House size={16} /></span>
                <div className="flex-1"><b>Rientro in lavanderia</b></div>
                <div className="text-right">
                  <div className="font-mono text-emerald-600 font-semibold">{fmtMin(giro.rientro_min)}</div>
                  <div className="text-xs text-slate-400 font-mono">{giro.rientro_km} km</div>
                </div>
              </div>
            </div>
            <GiroMappa giro={giro} />
          </div>
        </div>
      )}

      {giro && giro.senza_indirizzo.length > 0 && (
        <div className="kpi-card p-4 border-amber-300 bg-amber-50" data-testid="senza-indirizzo-panel">
          <h4 className="font-bold text-sm text-amber-700 flex items-center gap-2 mb-2"><Warning size={18} />Consegne escluse dal giro</h4>
          {giro.senza_indirizzo.map(c => (
            <div key={c.cliente_id} className="text-sm text-amber-800">• {c.cliente} — {c.motivo} <span className="text-xs">(completa l'indirizzo di scarico in Clienti)</span></div>
          ))}
        </div>
      )}
    </div>
  );
}
