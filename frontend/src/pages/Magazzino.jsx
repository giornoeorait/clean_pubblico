import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import {
  Package, Plus, Warning, PlusCircle, MinusCircle, ArrowsClockwise,
  Flask, ShieldCheck, Drop, Tray, ClockCountdown, XCircle,
} from "@phosphor-icons/react";
import { toast } from "sonner";

const CAT_ICON = {
  detergente: Drop,
  dpi: ShieldCheck,
  chimico: Flask,
  consumabile: Tray,
  altro: Package,
};

const CAT_COLOR = {
  detergente: "from-azzurro/20 to-azzurro/10 text-azzurro",
  dpi: "from-indaco/20 to-indaco/10 text-indaco",
  chimico: "from-amber-200 to-amber-100 text-amber-700",
  consumabile: "from-slate-200 to-slate-100 text-slate-700",
  altro: "from-slate-200 to-slate-100 text-slate-600",
};

const STATO_CLS = {
  ok: "bg-emerald-100 text-emerald-700 border border-emerald-200",
  bassa: "bg-amber-100 text-amber-700 border border-amber-200",
  esaurita: "bg-red-100 text-red-700 border border-red-200",
};

const SCAD_CLS = {
  ok: "text-slate-500",
  prossima: "text-amber-600 font-semibold",
  scaduto: "text-red-600 font-bold",
  na: "text-slate-300",
};

const EMPTY = {
  codice: "", descrizione: "", categoria: "detergente", unita_misura: "L",
  scorta_attuale: 0, scorta_minima: 0, prezzo_unitario: 0,
  fornitore: "", scadenza: "", note: "",
};

const MOV_EMPTY = { tipo: "scarico", quantita: 0, motivo: "", lotto_fornitore: "", note: "" };

export default function Magazzino() {
  const [list, setList] = useState([]);
  const [allarmi, setAllarmi] = useState(null);
  const [filterCat, setFilterCat] = useState("");
  const [filterAll, setFilterAll] = useState(false);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [editingId, setEditingId] = useState(null);
  // movimento modal
  const [movOpen, setMovOpen] = useState(false);
  const [movForm, setMovForm] = useState(MOV_EMPTY);
  const [movItem, setMovItem] = useState(null);
  const [movHistory, setMovHistory] = useState([]);

  const fetch = async () => {
    const params = [];
    if (filterCat) params.push(`categoria=${filterCat}`);
    if (filterAll) params.push(`solo_allarmi=true`);
    const q = params.length ? `?${params.join("&")}` : "";
    const [l, a] = await Promise.all([api.get(`/magazzino${q}`), api.get("/magazzino/allarmi")]);
    setList(l.data); setAllarmi(a.data);
  };
  useEffect(() => { fetch(); }, [filterCat, filterAll]);

  const save = async (e) => {
    e.preventDefault();
    try {
      const payload = { ...form };
      if (!payload.scadenza) delete payload.scadenza;
      if (editingId) await api.patch(`/magazzino/${editingId}`, payload);
      else await api.post("/magazzino", payload);
      toast.success("Articolo salvato"); setOpen(false); setForm(EMPTY); setEditingId(null); fetch();
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const edit = (it) => {
    setForm({
      ...EMPTY, ...it,
      scadenza: it.scadenza ? String(it.scadenza).slice(0, 10) : "",
    });
    setEditingId(it.id); setOpen(true);
  };

  const openMov = async (it) => {
    setMovItem(it); setMovForm(MOV_EMPTY);
    const { data } = await api.get(`/magazzino/${it.id}/movimenti`);
    setMovHistory(data); setMovOpen(true);
  };

  const submitMov = async (e) => {
    e.preventDefault();
    try {
      await api.post(`/magazzino/${movItem.id}/movimento`, { ...movForm, quantita: Number(movForm.quantita) });
      toast.success(`${movForm.tipo} registrato`);
      setMovForm(MOV_EMPTY);
      const { data } = await api.get(`/magazzino/${movItem.id}/movimenti`);
      setMovHistory(data);
      fetch();
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const quickAdjust = async (it, tipo, qta = 1) => {
    await api.post(`/magazzino/${it.id}/movimento`, { tipo, quantita: qta, motivo: "quick-adj", note: "" });
    fetch();
  };

  const totValore = list.reduce((s, it) => s + (it.scorta_attuale || 0) * (it.prezzo_unitario || 0), 0);

  return (
    <div>
      <PageHeader
        eyebrow="WMS"
        title="Magazzino — Detergenti & DPI"
        subtitle="Scorta real-time, soglie minime, allarmi scadenza. Carico/scarico tracciato per singolo articolo."
        actions={
          <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setEditingId(null); setForm(EMPTY); } }}>
            <DialogTrigger asChild>
              <Button className="bg-indaco hover:bg-indaco-dark" data-testid="new-magazzino-btn"><Plus size={16} className="mr-1" />Nuovo Articolo</Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl">
              <DialogHeader><DialogTitle>{editingId ? "Modifica articolo" : "Nuovo articolo magazzino"}</DialogTitle></DialogHeader>
              <form onSubmit={save} className="grid grid-cols-2 gap-4">
                <div><Label>Codice *</Label><Input required value={form.codice} onChange={e => setForm({...form, codice: e.target.value})} data-testid="mag-codice" /></div>
                <div>
                  <Label>Categoria</Label>
                  <Select value={form.categoria} onValueChange={v => setForm({...form, categoria: v})}>
                    <SelectTrigger data-testid="mag-categoria"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="detergente">Detergente</SelectItem>
                      <SelectItem value="dpi">DPI</SelectItem>
                      <SelectItem value="chimico">Chimico</SelectItem>
                      <SelectItem value="consumabile">Consumabile</SelectItem>
                      <SelectItem value="altro">Altro</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="col-span-2"><Label>Descrizione *</Label><Input required value={form.descrizione} onChange={e => setForm({...form, descrizione: e.target.value})} /></div>
                <div>
                  <Label>Unità di misura</Label>
                  <Select value={form.unita_misura} onValueChange={v => setForm({...form, unita_misura: v})}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="pz">Pezzi</SelectItem>
                      <SelectItem value="kg">Kg</SelectItem>
                      <SelectItem value="L">Litri</SelectItem>
                      <SelectItem value="m">Metri</SelectItem>
                      <SelectItem value="conf">Confezioni</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div><Label>Fornitore</Label><Input value={form.fornitore} onChange={e => setForm({...form, fornitore: e.target.value})} /></div>
                {!editingId && <div><Label>Scorta iniziale</Label><Input type="number" step="0.01" value={form.scorta_attuale} onChange={e => setForm({...form, scorta_attuale: parseFloat(e.target.value) || 0})} /></div>}
                {editingId && <div className="opacity-50"><Label>Scorta attuale (usa movimenti)</Label><Input disabled value={form.scorta_attuale} /></div>}
                <div><Label>Scorta minima</Label><Input type="number" step="0.01" value={form.scorta_minima} onChange={e => setForm({...form, scorta_minima: parseFloat(e.target.value) || 0})} data-testid="mag-scorta-minima" /></div>
                <div><Label>Prezzo unitario (€)</Label><Input type="number" step="0.01" value={form.prezzo_unitario} onChange={e => setForm({...form, prezzo_unitario: parseFloat(e.target.value) || 0})} /></div>
                <div><Label>Scadenza</Label><Input type="date" value={form.scadenza} onChange={e => setForm({...form, scadenza: e.target.value})} /></div>
                <div className="col-span-2"><Label>Note</Label><Textarea rows={2} value={form.note} onChange={e => setForm({...form, note: e.target.value})} /></div>
                <div className="col-span-2 flex justify-end gap-2">
                  <Button type="button" variant="outline" onClick={() => setOpen(false)}>Annulla</Button>
                  <Button type="submit" className="bg-indaco hover:bg-indaco-dark" data-testid="save-magazzino-btn">Salva</Button>
                </div>
              </form>
            </DialogContent>
          </Dialog>
        }
      />

      {/* KPI Allarmi */}
      {allarmi && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
          <div className={`kpi-card ${allarmi.totale > 0 ? "ring-2 ring-red-300" : ""}`} data-testid="kpi-allarmi-totale">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-red-100 flex items-center justify-center"><Warning size={20} weight="duotone" className="text-red-600" /></div>
              <div><div className="overline">In allarme</div><div className="font-display text-2xl font-bold">{allarmi.totale}</div></div>
            </div>
          </div>
          <div className="kpi-card">
            <div className="overline">Esauriti</div>
            <div className="font-display text-2xl font-bold text-red-600">{allarmi.scorta_esaurita}</div>
          </div>
          <div className="kpi-card">
            <div className="overline">Scorta bassa</div>
            <div className="font-display text-2xl font-bold text-amber-600">{allarmi.scorta_bassa}</div>
          </div>
          <div className="kpi-card">
            <div className="overline">Scadenza &lt; 30gg</div>
            <div className="font-display text-2xl font-bold text-amber-600">{allarmi.scadenza_prossima}</div>
          </div>
          <div className="kpi-card">
            <div className="overline">Valore magazzino</div>
            <div className="font-display text-2xl font-bold">€ {totValore.toLocaleString("it-IT", { maximumFractionDigits: 0 })}</div>
          </div>
        </div>
      )}

      {/* Filtri */}
      <div className="flex flex-wrap gap-2 mb-6">
        <button onClick={() => { setFilterCat(""); setFilterAll(false); }} className={`px-3 py-1.5 text-xs font-semibold rounded-md ${!filterCat && !filterAll ? "bg-indaco text-white" : "bg-white border border-slate-200 text-slate-600"}`} data-testid="filter-all-mag">Tutti</button>
        <button onClick={() => { setFilterAll(true); setFilterCat(""); }} className={`px-3 py-1.5 text-xs font-semibold rounded-md ${filterAll ? "bg-red-500 text-white" : "bg-white border border-slate-200 text-slate-600 hover:border-red-400"}`} data-testid="filter-allarmi"><Warning size={12} className="inline mr-1" />Solo allarmi</button>
        {["detergente", "dpi", "chimico", "consumabile"].map(c => (
          <button key={c} onClick={() => { setFilterCat(c); setFilterAll(false); }} className={`px-3 py-1.5 text-xs font-semibold rounded-md capitalize ${filterCat === c ? "bg-indaco text-white" : "bg-white border border-slate-200 text-slate-600 hover:border-indaco"}`} data-testid={`filter-cat-${c}`}>{c}</button>
        ))}
      </div>

      {/* Grid articoli */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {list.map(it => {
          const Icon = CAT_ICON[it.categoria] || Package;
          const pct = it.scorta_minima > 0 ? Math.min(100, (it.scorta_attuale / (it.scorta_minima * 2)) * 100) : 100;
          return (
            <div key={it.id} className={`kpi-card ${it.in_allarme ? "ring-2 ring-red-200" : ""}`} data-testid={`mag-item-${it.codice}`}>
              <div className="flex items-start justify-between mb-3">
                <div className={`w-11 h-11 rounded-lg bg-gradient-to-br ${CAT_COLOR[it.categoria] || CAT_COLOR.altro} flex items-center justify-center`}>
                  <Icon size={22} weight="duotone" />
                </div>
                <div className="flex flex-col gap-1 items-end">
                  <span className={`stato-pill ${STATO_CLS[it.scorta_stato]}`}>{it.scorta_stato}</span>
                  {it.scadenza_stato !== "ok" && it.scadenza_stato !== "na" && (
                    <span className={`text-[10px] font-bold uppercase tracking-widest ${SCAD_CLS[it.scadenza_stato]}`}>
                      <ClockCountdown size={10} className="inline mr-0.5" />{it.scadenza_stato}
                    </span>
                  )}
                </div>
              </div>

              <div className="overline">{it.categoria} · {it.codice}</div>
              <div className="font-display text-lg font-bold mt-0.5 leading-tight">{it.descrizione}</div>

              <div className="mt-4 mb-1 flex items-baseline justify-between">
                <div>
                  <span className="font-display text-3xl font-bold">{it.scorta_attuale}</span>
                  <span className="text-sm text-slate-500 ml-1">{it.unita_misura}</span>
                </div>
                <div className="text-xs text-slate-500 font-mono">min {it.scorta_minima}</div>
              </div>
              <div className="w-full bg-slate-100 rounded-full h-1.5 overflow-hidden">
                <div className={`h-full ${it.scorta_stato === "esaurita" ? "bg-red-500" : it.scorta_stato === "bassa" ? "bg-amber-500" : "bg-emerald-500"} transition-all`} style={{ width: `${pct}%` }}></div>
              </div>

              <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
                <span>{it.fornitore || "—"}</span>
                {it.scadenza && <span className={SCAD_CLS[it.scadenza_stato]}><ClockCountdown size={12} className="inline mr-0.5" />{String(it.scadenza).slice(0, 10)}</span>}
              </div>

              <div className="mt-4 pt-3 border-t border-slate-100 grid grid-cols-3 gap-1">
                <button onClick={() => quickAdjust(it, "carico", 1)} className="py-1.5 text-xs bg-emerald-50 hover:bg-emerald-100 text-emerald-700 rounded flex items-center justify-center gap-1" data-testid={`carico-${it.codice}`}><PlusCircle size={14} weight="duotone" />+1</button>
                <button onClick={() => quickAdjust(it, "scarico", 1)} className="py-1.5 text-xs bg-red-50 hover:bg-red-100 text-red-700 rounded flex items-center justify-center gap-1" data-testid={`scarico-${it.codice}`}><MinusCircle size={14} weight="duotone" />−1</button>
                <button onClick={() => openMov(it)} className="py-1.5 text-xs bg-slate-50 hover:bg-slate-100 text-slate-700 rounded flex items-center justify-center gap-1" data-testid={`movimento-${it.codice}`}><ArrowsClockwise size={14} weight="duotone" />Movim.</button>
              </div>

              <button onClick={() => edit(it)} className="w-full mt-1 py-1.5 text-xs text-slate-400 hover:text-indaco">Modifica scheda</button>
            </div>
          );
        })}
        {list.length === 0 && <div className="col-span-3 text-center py-16 text-slate-400">Nessun articolo</div>}
      </div>

      {/* Modal movimento */}
      <Dialog open={movOpen} onOpenChange={setMovOpen}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          {movItem && (
            <>
              <DialogHeader>
                <DialogTitle className="font-display">
                  Movimento: {movItem.codice} — {movItem.descrizione}
                </DialogTitle>
              </DialogHeader>
              <div className="text-sm text-slate-500 mb-4">
                Scorta attuale: <span className="font-mono font-bold text-slate-900">{movItem.scorta_attuale} {movItem.unita_misura}</span> · min {movItem.scorta_minima}
              </div>

              <form onSubmit={submitMov} className="grid grid-cols-2 gap-3 p-4 bg-slate-50 rounded-lg mb-4">
                <div>
                  <Label>Tipo movimento</Label>
                  <Select value={movForm.tipo} onValueChange={v => setMovForm({...movForm, tipo: v})}>
                    <SelectTrigger data-testid="mov-tipo"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="carico">Carico (ingresso)</SelectItem>
                      <SelectItem value="scarico">Scarico (uso)</SelectItem>
                      <SelectItem value="rettifica">Rettifica inventario</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div><Label>Quantità</Label><Input type="number" step="0.01" required value={movForm.quantita} onChange={e => setMovForm({...movForm, quantita: e.target.value})} data-testid="mov-qta" /></div>
                <div><Label>Motivo</Label><Input value={movForm.motivo} onChange={e => setMovForm({...movForm, motivo: e.target.value})} placeholder="lavaggio / acquisto / smaltimento..." /></div>
                {movForm.tipo === "carico" && <div><Label>Lotto fornitore</Label><Input value={movForm.lotto_fornitore} onChange={e => setMovForm({...movForm, lotto_fornitore: e.target.value})} /></div>}
                <div className="col-span-2"><Label>Note</Label><Textarea rows={2} value={movForm.note} onChange={e => setMovForm({...movForm, note: e.target.value})} /></div>
                <div className="col-span-2"><Button type="submit" className="w-full bg-indaco hover:bg-indaco-dark" data-testid="submit-mov">Registra movimento</Button></div>
              </form>

              <div className="overline mb-3">Storico movimenti</div>
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {movHistory.map(m => {
                  const badgeCls = m.tipo === "carico" ? "bg-emerald-100 text-emerald-700" : m.tipo === "scarico" ? "bg-red-100 text-red-700" : "bg-slate-100 text-slate-700";
                  const sign = m.tipo === "carico" ? "+" : m.tipo === "scarico" ? "−" : "=";
                  return (
                    <div key={m.id} className="flex items-center gap-3 p-2 border border-slate-100 rounded-md text-sm">
                      <span className={`stato-pill capitalize ${badgeCls}`}>{m.tipo}</span>
                      <span className="font-mono font-bold">{sign}{m.quantita}</span>
                      <span className="text-slate-500 flex-1 text-xs">{m.motivo || "—"}</span>
                      <span className="text-xs text-slate-400 font-mono">{m.scorta_prima} → {m.scorta_dopo}</span>
                      <span className="text-xs text-slate-400 font-mono hidden md:inline">{new Date(m.timestamp).toLocaleDateString("it-IT")}</span>
                    </div>
                  );
                })}
                {movHistory.length === 0 && <div className="text-center py-6 text-slate-400 text-sm">Nessun movimento registrato</div>}
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
