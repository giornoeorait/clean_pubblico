import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import StatoBadge from "../components/StatoBadge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Checkbox } from "../components/ui/checkbox";
import {
  Wrench, Plus, Warning, ClockCountdown, Lightning, CheckCircle, HardDrives, CurrencyEur,
  Hammer, Package,
} from "@phosphor-icons/react";
import { toast } from "sonner";

const TICKET_TIPO_ICON = {
  guasto: Lightning,
  programmata: ClockCountdown,
  preventiva: Wrench,
  revisione: Hammer,
};

const PRIORITA_CLS = {
  bassa: "bg-slate-100 text-slate-700 border border-slate-200",
  media: "bg-sky-100 text-sky-700 border border-sky-200",
  alta: "bg-amber-100 text-amber-700 border border-amber-200",
  critica: "bg-red-100 text-red-700 border border-red-200 animate-pulse-dot",
};

const EMPTY = { macchina_id: "", tipo: "guasto", priorita: "media", titolo: "", descrizione: "", assegnato_a: "", fermo_macchina: false };
const IVT_EMPTY = { operatore: "", descrizione: "", durata_min: 30, pezzi_usati: [], costo: 0, note: "" };

export default function Manutenzione() {
  const [list, setList] = useState([]);
  const [macchine, setMacchine] = useState([]);
  const [filterStato, setFilterStato] = useState("");
  const [filterPrio, setFilterPrio] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [selected, setSelected] = useState(null);
  const [ivForm, setIvForm] = useState(IVT_EMPTY);
  const [pezziInput, setPezziInput] = useState("");

  const fetch = async () => {
    const params = [];
    if (filterStato) params.push(`stato=${filterStato}`);
    if (filterPrio) params.push(`priorita=${filterPrio}`);
    const q = params.length ? `?${params.join("&")}` : "";
    const [t, m] = await Promise.all([api.get(`/tickets${q}`), api.get("/macchine")]);
    setList(t.data); setMacchine(m.data);
  };
  useEffect(() => { fetch(); }, [filterStato, filterPrio]);

  const openDetail = async (t) => {
    const { data } = await api.get(`/tickets/${t.id}`);
    setSelected(data); setIvForm(IVT_EMPTY); setPezziInput("");
  };

  const save = async (e) => {
    e.preventDefault();
    if (!form.macchina_id || !form.titolo) { toast.error("Macchina e titolo sono obbligatori"); return; }
    try {
      await api.post("/tickets", form);
      toast.success("Ticket creato");
      setOpen(false); setForm(EMPTY); fetch();
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const changeStato = async (id, stato) => {
    await api.patch(`/tickets/${id}`, { stato });
    toast.success("Stato aggiornato");
    if (selected?.id === id) openDetail({ id });
    fetch();
  };

  const submitIntervento = async (e) => {
    e.preventDefault();
    const payload = {
      ...ivForm,
      pezzi_usati: pezziInput ? pezziInput.split(",").map(x => x.trim()).filter(Boolean) : [],
      durata_min: Number(ivForm.durata_min) || 0,
      costo: Number(ivForm.costo) || 0,
    };
    try {
      await api.post(`/tickets/${selected.id}/interventi`, payload);
      toast.success("Intervento registrato");
      setIvForm(IVT_EMPTY); setPezziInput("");
      const { data } = await api.get(`/tickets/${selected.id}`);
      setSelected(data);
      fetch();
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const counts = {
    aperto: list.filter(t => t.stato === "aperto").length,
    in_lavorazione: list.filter(t => t.stato === "in_lavorazione").length,
    risolto: list.filter(t => t.stato === "risolto" || t.stato === "chiuso").length,
    critici: list.filter(t => t.priorita === "critica" && t.stato !== "chiuso" && t.stato !== "risolto").length,
    costo: list.reduce((s, t) => s + (t.costo_totale || 0), 0),
  };

  return (
    <div>
      <PageHeader
        eyebrow="Asset Management"
        title="Manutenzione Macchine"
        subtitle="Ticket guasti, manutenzioni programmate e interventi tracciati con durata, pezzi e costi."
        actions={
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild><Button className="bg-indaco hover:bg-indaco-dark" data-testid="new-ticket-btn"><Plus size={16} className="mr-1" />Nuovo Ticket</Button></DialogTrigger>
            <DialogContent className="max-w-xl">
              <DialogHeader><DialogTitle>Apri ticket manutenzione</DialogTitle></DialogHeader>
              <form onSubmit={save} className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label>Macchina *</Label>
                    <Select value={form.macchina_id} onValueChange={v => setForm({...form, macchina_id: v})}>
                      <SelectTrigger data-testid="ticket-macchina"><SelectValue placeholder="Seleziona macchina" /></SelectTrigger>
                      <SelectContent>{macchine.map(m => <SelectItem key={m.id} value={m.id}>{m.codice} · {m.tipo}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Tipo</Label>
                    <Select value={form.tipo} onValueChange={v => setForm({...form, tipo: v})}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="guasto">Guasto</SelectItem>
                        <SelectItem value="programmata">Programmata</SelectItem>
                        <SelectItem value="preventiva">Preventiva</SelectItem>
                        <SelectItem value="revisione">Revisione</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label>Priorità</Label>
                    <Select value={form.priorita} onValueChange={v => setForm({...form, priorita: v})}>
                      <SelectTrigger data-testid="ticket-priorita"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="bassa">Bassa</SelectItem>
                        <SelectItem value="media">Media</SelectItem>
                        <SelectItem value="alta">Alta</SelectItem>
                        <SelectItem value="critica">Critica</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div><Label>Assegnato a</Label><Input value={form.assegnato_a} onChange={e => setForm({...form, assegnato_a: e.target.value})} placeholder="Tecnico/Fornitore" /></div>
                </div>
                <div><Label>Titolo *</Label><Input required value={form.titolo} onChange={e => setForm({...form, titolo: e.target.value})} data-testid="ticket-titolo" /></div>
                <div><Label>Descrizione</Label><Textarea rows={3} value={form.descrizione} onChange={e => setForm({...form, descrizione: e.target.value})} /></div>
                <label className="flex items-center gap-2 text-sm cursor-pointer">
                  <Checkbox checked={form.fermo_macchina} onCheckedChange={v => setForm({...form, fermo_macchina: !!v})} data-testid="ticket-fermo" />
                  <span>Macchina in fermo (imposta stato = guasto)</span>
                </label>
                <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setOpen(false)}>Annulla</Button><Button type="submit" className="bg-indaco hover:bg-indaco-dark">Apri ticket</Button></div>
              </form>
            </DialogContent>
          </Dialog>
        }
      />

      {/* KPI */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        <div className="kpi-card">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-red-100 flex items-center justify-center"><Warning size={20} weight="duotone" className="text-red-600" /></div>
            <div><div className="overline">Aperti</div><div className="font-display text-2xl font-bold text-red-600">{counts.aperto}</div></div>
          </div>
        </div>
        <div className="kpi-card">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center"><Wrench size={20} weight="duotone" className="text-amber-600" /></div>
            <div><div className="overline">In lavorazione</div><div className="font-display text-2xl font-bold text-amber-600">{counts.in_lavorazione}</div></div>
          </div>
        </div>
        <div className="kpi-card">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-emerald-100 flex items-center justify-center"><CheckCircle size={20} weight="duotone" className="text-emerald-600" /></div>
            <div><div className="overline">Risolti</div><div className="font-display text-2xl font-bold">{counts.risolto}</div></div>
          </div>
        </div>
        <div className="kpi-card">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-red-100 flex items-center justify-center"><Lightning size={20} weight="duotone" className="text-red-600" /></div>
            <div><div className="overline">Critici attivi</div><div className="font-display text-2xl font-bold text-red-600">{counts.critici}</div></div>
          </div>
        </div>
        <div className="kpi-card">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-indaco/10 flex items-center justify-center"><CurrencyEur size={20} weight="duotone" className="text-indaco" /></div>
            <div><div className="overline">Costi totali</div><div className="font-display text-2xl font-bold">€ {counts.costo.toLocaleString("it-IT", { maximumFractionDigits: 0 })}</div></div>
          </div>
        </div>
      </div>

      {/* Filtri */}
      <div className="flex flex-wrap gap-2 mb-6">
        <div className="flex gap-1">
          {["", "aperto", "in_lavorazione", "risolto", "chiuso"].map(s => (
            <button key={s || "tutti"} onClick={() => setFilterStato(s)} className={`px-3 py-1.5 text-xs font-semibold rounded-md capitalize ${filterStato === s ? "bg-indaco text-white" : "bg-white border border-slate-200 text-slate-600 hover:border-indaco"}`} data-testid={`filter-stato-${s || "all"}`}>{s || "Tutti"}</button>
          ))}
        </div>
        <div className="flex gap-1 ml-auto">
          {["", "bassa", "media", "alta", "critica"].map(p => (
            <button key={p || "prio-all"} onClick={() => setFilterPrio(p)} className={`px-3 py-1.5 text-xs font-semibold rounded-md capitalize ${filterPrio === p ? "bg-slate-900 text-white" : "bg-white border border-slate-200 text-slate-600"}`}>{p || "Priorità"}</button>
          ))}
        </div>
      </div>

      {/* Lista tickets */}
      <div className="space-y-3">
        {list.map(t => {
          const Icon = TICKET_TIPO_ICON[t.tipo] || Wrench;
          const isOpen = t.stato === "aperto" || t.stato === "in_lavorazione";
          return (
            <div key={t.id} className={`kpi-card flex flex-col md:flex-row md:items-center gap-4 cursor-pointer hover:border-indaco ${t.priorita === "critica" && isOpen ? "ring-2 ring-red-200" : ""}`} onClick={() => openDetail(t)} data-testid={`ticket-${t.numero}`}>
              <div className={`w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0 ${isOpen ? "bg-red-100 text-red-600" : "bg-emerald-100 text-emerald-700"}`}>
                <Icon size={22} weight="duotone" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono font-bold text-indaco text-sm">{t.numero}</span>
                  <span className="text-xs font-mono text-slate-500">· {t.macchina_codice}</span>
                  <span className={`stato-pill capitalize ${PRIORITA_CLS[t.priorita]}`}>{t.priorita}</span>
                  <StatoBadge stato={t.stato} />
                  {t.fermo_macchina && isOpen && <span className="stato-pill bg-red-600 text-white border border-red-700">Fermo</span>}
                </div>
                <div className="font-display font-bold mt-1">{t.titolo}</div>
                <div className="text-xs text-slate-500 mt-0.5 line-clamp-1">{t.descrizione || "—"}</div>
              </div>
              <div className="flex flex-col items-end text-xs font-mono gap-1">
                <span className="text-slate-400 uppercase tracking-widest text-[10px]">{t.interventi_count || 0} interv.</span>
                <span className="font-bold text-slate-900">{(t.durata_totale_min || 0)} min</span>
                <span className="text-indaco">€ {(t.costo_totale || 0).toFixed(2)}</span>
              </div>
            </div>
          );
        })}
        {list.length === 0 && <div className="kpi-card text-center py-12 text-slate-400">Nessun ticket</div>}
      </div>

      {/* Detail dialog */}
      <Dialog open={!!selected} onOpenChange={(o) => !o && setSelected(null)}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          {selected && (
            <>
              <DialogHeader>
                <DialogTitle className="font-display flex items-center gap-2">
                  <Wrench size={20} className="text-indaco" weight="duotone" />
                  {selected.numero} · {selected.titolo}
                </DialogTitle>
              </DialogHeader>

              <div className="grid grid-cols-4 gap-3 mb-4 mt-2 text-sm">
                <div><div className="overline">Macchina</div><div className="font-mono font-bold">{selected.macchina_codice}</div></div>
                <div><div className="overline">Tipo</div><div className="capitalize">{selected.tipo}</div></div>
                <div><div className="overline">Priorità</div><StatoBadge stato={selected.priorita} /></div>
                <div><div className="overline">Stato</div><StatoBadge stato={selected.stato} /></div>
              </div>

              <div className="bg-slate-50 p-3 rounded-md text-sm mb-4">{selected.descrizione || "—"}</div>

              {/* Quick actions */}
              <div className="flex flex-wrap gap-2 mb-6">
                {selected.stato === "aperto" && <Button size="sm" variant="outline" onClick={() => changeStato(selected.id, "in_lavorazione")} data-testid="btn-start">Avvia lavorazione</Button>}
                {(selected.stato === "aperto" || selected.stato === "in_lavorazione") && <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700" onClick={() => changeStato(selected.id, "risolto")} data-testid="btn-resolve">Risolvi</Button>}
                {selected.stato === "risolto" && <Button size="sm" variant="outline" onClick={() => changeStato(selected.id, "chiuso")} data-testid="btn-close">Chiudi ticket</Button>}
              </div>

              {/* Nuovo intervento */}
              {selected.stato !== "chiuso" && (
                <form onSubmit={submitIntervento} className="bg-indaco/5 border border-indaco/20 rounded-md p-4 mb-6">
                  <div className="overline mb-3 text-indaco">Registra intervento</div>
                  <div className="grid grid-cols-2 gap-3">
                    <div><Label>Operatore *</Label><Input required value={ivForm.operatore} onChange={e => setIvForm({...ivForm, operatore: e.target.value})} data-testid="iv-operatore" /></div>
                    <div><Label>Durata (min)</Label><Input type="number" value={ivForm.durata_min} onChange={e => setIvForm({...ivForm, durata_min: e.target.value})} /></div>
                    <div className="col-span-2"><Label>Descrizione *</Label><Textarea required rows={2} value={ivForm.descrizione} onChange={e => setIvForm({...ivForm, descrizione: e.target.value})} /></div>
                    <div><Label>Pezzi usati (virgole)</Label><Input value={pezziInput} onChange={e => setPezziInput(e.target.value)} placeholder="Filtro X, Guarnizione Y" /></div>
                    <div><Label>Costo €</Label><Input type="number" step="0.01" value={ivForm.costo} onChange={e => setIvForm({...ivForm, costo: e.target.value})} /></div>
                  </div>
                  <Button type="submit" className="w-full mt-4 bg-indaco hover:bg-indaco-dark" data-testid="submit-intervento">Salva intervento</Button>
                </form>
              )}

              {/* Storico interventi timeline */}
              <div className="overline mb-3">Storico interventi ({selected.interventi?.length || 0})</div>
              <div className="relative pl-6 space-y-4">
                {(selected.interventi || []).map((iv, i) => (
                  <div key={iv.id} className="relative">
                    <div className="absolute -left-6 top-1 w-3 h-3 rounded-full bg-indaco ring-4 ring-indaco/20"></div>
                    {i < selected.interventi.length - 1 && <div className="absolute -left-[18px] top-4 bottom-0 w-0.5 bg-slate-200"></div>}
                    <div className="text-xs text-slate-500 font-mono">{new Date(iv.data_intervento).toLocaleString("it-IT")} · {iv.operatore}</div>
                    <div className="text-sm mt-0.5">{iv.descrizione}</div>
                    <div className="flex flex-wrap gap-3 mt-1 text-xs text-slate-500 font-mono">
                      <span>{iv.durata_min} min</span>
                      {iv.costo > 0 && <span className="text-indaco font-bold">€ {iv.costo.toFixed(2)}</span>}
                      {iv.pezzi_usati?.length > 0 && <span className="flex items-center gap-1"><Package size={11} />{iv.pezzi_usati.join(", ")}</span>}
                    </div>
                  </div>
                ))}
                {(selected.interventi || []).length === 0 && <div className="text-sm text-slate-400 py-4">Nessun intervento registrato</div>}
              </div>

              <div className="mt-6 pt-4 border-t border-slate-200 flex justify-between text-sm">
                <div className="font-mono text-slate-500">Totale: {selected.durata_totale_min || 0} min</div>
                <div className="font-display font-bold text-xl text-indaco">€ {(selected.costo_totale || 0).toFixed(2)}</div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
