import React, { useCallback, useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import {
  Plus, Trash, FloppyDisk, Truck, CalendarBlank, Clipboard, ArrowSquareOut,
  Note, CheckCircle, XCircle,
} from "@phosphor-icons/react";
import { toast } from "sonner";

const STATO_CLASS = {
  nuovo: "bg-indaco/10 text-indaco",
  in_lavorazione: "bg-amber-100 text-amber-700",
  convertito_ddt: "bg-emerald-100 text-emerald-700",
  annullato: "bg-red-100 text-red-700",
};
const STATO_LBL = { nuovo: "Nuovo", in_lavorazione: "In lavorazione", convertito_ddt: "DDT generato", annullato: "Annullato" };

function inDays(n) { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); }

export default function Ordinativi() {
  const [list, setList] = useState([]);
  const [clienti, setClienti] = useState([]);
  const [articoli, setArticoli] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(null);
  const [filterStato, setFilterStato] = useState("all");

  const fetchAll = useCallback(async () => {
    const q = filterStato === "all" ? "" : `?stato=${filterStato}`;
    const [o, c, a] = await Promise.all([
      api.get(`/ordinativi${q}`), api.get("/clienti"), api.get("/articoli"),
    ]);
    setList(o.data); setClienti(c.data); setArticoli(a.data);
  }, [filterStato]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const openNew = () => {
    setEditing(null);
    setForm({ cliente_id: "", data_consegna_richiesta: inDays(3), righe: [], note_interne: "" });
    setOpen(true);
  };
  const openEdit = (o) => {
    setEditing(o);
    setForm({
      cliente_id: o.cliente_id,
      data_consegna_richiesta: o.data_consegna_richiesta || inDays(3),
      righe: o.righe.map(r => ({ articolo_id: r.articolo_id, quantita: r.quantita })),
      note_interne: o.note_interne || "",
    });
    setOpen(true);
  };

  const addRiga = () => setForm({ ...form, righe: [...form.righe, { articolo_id: "", quantita: 1 }] });
  const updRiga = (i, k, v) => setForm({ ...form, righe: form.righe.map((r, j) => j === i ? { ...r, [k]: v } : r) });
  const delRiga = (i) => setForm({ ...form, righe: form.righe.filter((_, j) => j !== i) });

  const save = async () => {
    if (!form.cliente_id) { toast.error("Seleziona cliente"); return; }
    if (!form.righe.length) { toast.error("Aggiungi righe"); return; }
    const bad = form.righe.find(r => !r.articolo_id || !r.quantita || r.quantita <= 0);
    if (bad) { toast.error("Ogni riga deve avere articolo e quantità"); return; }
    try {
      const payload = {
        cliente_id: form.cliente_id,
        data_consegna_richiesta: form.data_consegna_richiesta,
        righe: form.righe.map(r => ({ articolo_id: r.articolo_id, quantita: parseInt(r.quantita) || 0 })),
        note_interne: form.note_interne,
      };
      if (editing) {
        const { cliente_id: _, ...patch } = payload;
        await api.patch(`/ordinativi/${editing.id}`, patch);
        toast.success("Ordinativo aggiornato");
      } else {
        const { data } = await api.post("/ordinativi", payload);
        toast.success(`${data.numero} creato — € ${data.totale.toFixed(2)}`);
      }
      setOpen(false); fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const cambiaStato = async (o, nuovo) => {
    try { await api.patch(`/ordinativi/${o.id}`, { stato: nuovo }); toast.success(`Stato: ${STATO_LBL[nuovo]}`); fetchAll(); }
    catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const convertiDDT = async (o) => {
    if (!window.confirm(`Trasformare ${o.numero} in DDT?`)) return;
    try {
      const { data } = await api.post(`/ordinativi/${o.id}/converti-ddt`);
      toast.success(`DDT ${data.ddt_numero} creato`);
      fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const delOrd = async (o) => {
    if (!window.confirm(`Eliminare ${o.numero}?`)) return;
    try { await api.delete(`/ordinativi/${o.id}`); toast.success("Eliminato"); fetchAll(); }
    catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const preview = (form?.righe || []).reduce((acc, r) => {
    const a = articoli.find(x => x.id === r.articolo_id);
    if (!a) return acc;
    const p = a.prezzo_lavaggio || a.prezzo || 0;
    return acc + p * (r.quantita || 0);
  }, 0);

  return (
    <div>
      <PageHeader
        eyebrow="Commerciale"
        title="Ordinativi"
        subtitle="Richieste di consegna dai clienti (interne o dal portale pubblico). Trasformabili in D.D.T. con un click."
        actions={
          <Button onClick={openNew} className="bg-indaco hover:bg-indaco-dark" data-testid="new-ord-btn">
            <Plus size={16} className="mr-1" weight="bold" />Nuovo ordinativo
          </Button>
        }
      />

      <div className="kpi-card mb-4 p-3 flex gap-2 items-center">
        <Label className="text-sm text-slate-500 m-0">Filtra stato:</Label>
        <Select value={filterStato} onValueChange={setFilterStato}>
          <SelectTrigger className="w-60 h-9" data-testid="ord-filter-stato"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tutti</SelectItem>
            <SelectItem value="nuovo">Nuovi</SelectItem>
            <SelectItem value="in_lavorazione">In lavorazione</SelectItem>
            <SelectItem value="convertito_ddt">DDT generato</SelectItem>
            <SelectItem value="annullato">Annullati</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="kpi-card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Numero</th>
                <th>Cliente</th>
                <th>Origine</th>
                <th>Richiesto per</th>
                <th>Totale</th>
                <th>Stato</th>
                <th>Azioni</th>
              </tr>
            </thead>
            <tbody>
              {list.map(o => {
                const cli = clienti.find(c => c.id === o.cliente_id);
                return (
                  <tr key={o.id} data-testid={`ord-row-${o.id}`}>
                    <td>
                      <div className="font-mono font-bold">{o.numero}</div>
                      {o.ddt_numero && <div className="text-[11px] text-emerald-700 font-mono">→ {o.ddt_numero}</div>}
                    </td>
                    <td className="text-sm">
                      <div>{cli?.ragione_sociale || o.cliente_snapshot?.ragione_sociale || "—"}</div>
                      {(cli?.denominazione_struttura || o.cliente_snapshot?.denominazione_struttura) && (
                        <div className="text-xs text-slate-500">{cli?.denominazione_struttura || o.cliente_snapshot?.denominazione_struttura}</div>
                      )}
                    </td>
                    <td>
                      <span className={`text-[11px] px-2 py-0.5 rounded ${o.origine === "portale" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>
                        {o.origine === "portale" ? "Portale cliente" : "Interno"}
                      </span>
                    </td>
                    <td className="text-xs">{o.data_consegna_richiesta ? new Date(o.data_consegna_richiesta).toLocaleDateString("it-IT") : "—"}</td>
                    <td className="font-mono font-bold text-indaco">€ {o.totale.toFixed(2)}</td>
                    <td><span className={`px-2 py-0.5 text-xs rounded-full ${STATO_CLASS[o.stato]}`}>{STATO_LBL[o.stato]}</span></td>
                    <td>
                      <div className="flex items-center gap-0.5">
                        {o.stato !== "convertito_ddt" && (
                          <>
                            <Button variant="ghost" size="icon" onClick={() => openEdit(o)} title="Modifica"><Note size={13} /></Button>
                            {o.stato === "nuovo" && (
                              <Button variant="ghost" size="icon" onClick={() => cambiaStato(o, "in_lavorazione")} title="In lavorazione" className="text-amber-600"><Clipboard size={13} /></Button>
                            )}
                            {(o.stato === "nuovo" || o.stato === "in_lavorazione") && (
                              <Button variant="ghost" size="icon" onClick={() => convertiDDT(o)} title="Trasforma in DDT" className="text-emerald-600" data-testid={`convert-ord-${o.id}`}><Truck size={14} weight="fill" /></Button>
                            )}
                            {o.stato !== "annullato" && (
                              <Button variant="ghost" size="icon" onClick={() => cambiaStato(o, "annullato")} title="Annulla" className="text-red-500"><XCircle size={13} /></Button>
                            )}
                            <Button variant="ghost" size="icon" onClick={() => delOrd(o)} title="Elimina" className="text-red-600"><Trash size={13} /></Button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {list.length === 0 && (
                <tr><td colSpan={7} className="text-center py-16 text-slate-400">
                  <Truck size={32} className="mx-auto mb-2 text-slate-300" weight="duotone" />
                  Nessun ordinativo.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setEditing(null); setForm(null); } }}>
        <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editing ? `Modifica ${editing.numero}` : "Nuovo ordinativo"}</DialogTitle></DialogHeader>
          {form && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2">
                  <Label>Cliente *</Label>
                  <Select value={form.cliente_id} onValueChange={v => setForm({...form, cliente_id: v})} disabled={!!editing}>
                    <SelectTrigger data-testid="ord-cliente"><SelectValue placeholder="Seleziona cliente…" /></SelectTrigger>
                    <SelectContent>{clienti.map(c => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Data consegna richiesta</Label>
                  <Input type="date" value={form.data_consegna_richiesta} onChange={e => setForm({...form, data_consegna_richiesta: e.target.value})} data-testid="ord-data" />
                </div>
                <div>
                  <Label>Note interne</Label>
                  <Input value={form.note_interne} onChange={e => setForm({...form, note_interne: e.target.value})} />
                </div>
              </div>

              <section className="border border-slate-200 rounded-lg overflow-hidden">
                <div className="flex items-center justify-between px-4 py-2 bg-slate-50 border-b border-slate-200">
                  <h4 className="font-display font-bold text-sm">Articoli</h4>
                  <Button type="button" variant="outline" size="sm" onClick={addRiga}><Plus size={13} className="mr-1" />Riga</Button>
                </div>
                <table className="w-full text-sm">
                  <thead className="text-xs uppercase tracking-wide text-slate-500 border-b border-slate-200">
                    <tr><th className="p-2 text-left">Articolo</th><th>Q.tà</th><th className="text-right">Preview</th><th></th></tr>
                  </thead>
                  <tbody>
                    {form.righe.map((r, i) => {
                      const a = articoli.find(x => x.id === r.articolo_id);
                      const p = a?.prezzo_lavaggio || a?.prezzo || 0;
                      return (
                        <tr key={i} className="border-b border-slate-100">
                          <td className="p-2">
                            <Select value={r.articolo_id} onValueChange={v => updRiga(i, "articolo_id", v)}>
                              <SelectTrigger className="h-8"><SelectValue placeholder="Articolo…" /></SelectTrigger>
                              <SelectContent>{articoli.map(x => <SelectItem key={x.id} value={x.id}>{x.codice} · {x.descrizione}</SelectItem>)}</SelectContent>
                            </Select>
                          </td>
                          <td>
                            <Input
                              type="number"
                              step={Math.max(1, parseInt(a?.multiplo_quantita) || 1)}
                              min={0}
                              className="h-8 w-20 text-right font-mono"
                              value={r.quantita}
                              onChange={e => {
                                const step = Math.max(1, parseInt(a?.multiplo_quantita) || 1);
                                const v = parseInt(e.target.value) || 0;
                                const snapped = step > 1 ? Math.floor(v / step) * step : v;
                                updRiga(i, "quantita", snapped);
                              }}
                            />
                            {a?.multiplo_quantita > 1 && (
                              <div className="text-[10px] text-amber-600 font-mono mt-0.5">multipli di {a.multiplo_quantita}</div>
                            )}
                          </td>
                          <td className="text-right text-xs font-mono">
                            <div className="text-slate-600">€ {p.toFixed(2)}/{a?.unita_misura || "pz"}</div>
                            <div className="text-indaco font-bold">€ {(p * (r.quantita || 0)).toFixed(2)}</div>
                          </td>
                          <td><Button variant="ghost" size="icon" onClick={() => delRiga(i)} className="text-red-500"><Trash size={13} /></Button></td>
                        </tr>
                      );
                    })}
                    {form.righe.length === 0 && <tr><td colSpan={4} className="p-4 text-center text-slate-400 text-xs">Aggiungi righe</td></tr>}
                  </tbody>
                  <tfoot className="bg-indaco/5 border-t-2 border-indaco">
                    <tr>
                      <td colSpan={2} className="p-2 text-right font-semibold">Totale stimato:</td>
                      <td className="text-right font-mono font-bold text-indaco">€ {preview.toFixed(2)}</td>
                      <td></td>
                    </tr>
                  </tfoot>
                </table>
              </section>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-200">
                <Button type="button" variant="outline" onClick={() => setOpen(false)}>Annulla</Button>
                <Button onClick={save} className="bg-indaco hover:bg-indaco-dark" data-testid="save-ord-btn">
                  <FloppyDisk size={14} className="mr-1" />{editing ? "Aggiorna" : "Crea ordinativo"}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
