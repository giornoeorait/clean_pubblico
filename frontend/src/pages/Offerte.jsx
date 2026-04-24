import React, { useCallback, useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import {
  Plus, FilePdf, Trash, PencilSimple, HandHeart, FileText, FloppyDisk,
  CheckCircle, XCircle, Eye, Handshake, Copy, ArrowRight, Warning,
} from "@phosphor-icons/react";
import { toast } from "sonner";

const STATO_CLASS = {
  bozza: "bg-slate-100 text-slate-700",
  inviata: "bg-indaco/10 text-indaco",
  accettata: "bg-emerald-100 text-emerald-700",
  rifiutata: "bg-red-100 text-red-700",
  contratto: "bg-amber-100 text-amber-700",
};
const STATO_LBL = { bozza: "Bozza", inviata: "Inviata", accettata: "Accettata", rifiutata: "Rifiutata", contratto: "Contratto" };

function todayIso() { return new Date().toISOString().slice(0, 10); }
function inDays(n) { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); }

export default function Offerte() {
  const [list, setList] = useState([]);
  const [clienti, setClienti] = useState([]);
  const [articoli, setArticoli] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(null);

  const fetchAll = useCallback(async () => {
    const [o, c, a, t] = await Promise.all([
      api.get("/offerte"),
      api.get("/clienti"),
      api.get("/articoli"),
      api.get("/termini-templates"),
    ]);
    setList(o.data); setClienti(c.data); setArticoli(a.data); setTemplates(t.data);
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const openNew = () => {
    setEditing(null);
    setForm({
      cliente_id: "",
      durata_mesi: 12,
      data_scadenza: inDays(30),
      note: "",
      termini_condizioni: [],
      righe: [],
    });
    setOpen(true);
  };

  const openEdit = (o) => {
    setEditing(o);
    setForm({
      cliente_id: o.cliente_id,
      durata_mesi: o.durata_mesi,
      data_scadenza: o.data_scadenza || "",
      note: o.note || "",
      termini_condizioni: [...(o.termini_condizioni || [])],
      righe: (o.righe || []).map(r => ({
        articolo_id: r.articolo_id,
        quantita: r.quantita,
        sconto_perc: r.sconto_perc,
        sconto_eur: r.sconto_eur,
      })),
    });
    setOpen(true);
  };

  const selectedCliente = clienti.find(c => c.id === form?.cliente_id);

  const addRiga = () => setForm({ ...form, righe: [...form.righe, { articolo_id: "", quantita: 1, sconto_perc: 0, sconto_eur: 0 }] });
  const delRiga = (i) => setForm({ ...form, righe: form.righe.filter((_, j) => j !== i) });
  const updRiga = (i, k, v) => setForm({ ...form, righe: form.righe.map((r, j) => j === i ? { ...r, [k]: v } : r) });

  const addTermine = () => setForm({ ...form, termini_condizioni: [...form.termini_condizioni, { titolo: "", testo: "" }] });
  const delTermine = (i) => setForm({ ...form, termini_condizioni: form.termini_condizioni.filter((_, j) => j !== i) });
  const updTermine = (i, k, v) => setForm({ ...form, termini_condizioni: form.termini_condizioni.map((t, j) => j === i ? { ...t, [k]: v } : t) });
  const addTemplate = (t) => {
    if (form.termini_condizioni.some(x => x.titolo === t.titolo)) { toast.info("Già inserito"); return; }
    setForm({ ...form, termini_condizioni: [...form.termini_condizioni, { titolo: t.titolo, testo: t.testo }] });
  };

  const save = async () => {
    if (!form.cliente_id) { toast.error("Seleziona cliente"); return; }
    if (!form.righe.length) { toast.error("Aggiungi almeno una riga"); return; }
    const bad = form.righe.find(r => !r.articolo_id || !r.quantita || r.quantita <= 0);
    if (bad) { toast.error("Ogni riga deve avere articolo e quantità > 0"); return; }
    const payload = {
      cliente_id: form.cliente_id,
      durata_mesi: parseInt(form.durata_mesi) || 12,
      data_scadenza: form.data_scadenza || null,
      note: form.note,
      termini_condizioni: form.termini_condizioni.filter(t => t.titolo && t.testo),
      righe: form.righe.map(r => ({
        articolo_id: r.articolo_id,
        quantita: parseFloat(r.quantita) || 0,
        sconto_perc: parseFloat(r.sconto_perc) || 0,
        sconto_eur: parseFloat(r.sconto_eur) || 0,
      })),
    };
    try {
      if (editing) {
        const { cliente_id: _, ...patch } = payload;
        await api.patch(`/offerte/${editing.id}`, patch);
        toast.success("Offerta aggiornata");
      } else {
        const { data } = await api.post("/offerte", payload);
        toast.success(`Offerta ${data.numero} creata — € ${data.imponibile.toFixed(2)}`);
      }
      setOpen(false); fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const cambiaStato = async (o, nuovo) => {
    try { await api.patch(`/offerte/${o.id}`, { stato: nuovo }); toast.success(`Stato: ${nuovo}`); fetchAll(); }
    catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const converti = async (o) => {
    if (!window.confirm(`Trasformare ${o.numero} in contratto? Operazione irreversibile.`)) return;
    try {
      const { data } = await api.post(`/offerte/${o.id}/converti-contratto`);
      toast.success(`Contratto ${data.contratto_numero} attivato`);
      fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const delOff = async (o) => {
    if (!window.confirm(`Eliminare ${o.numero}?`)) return;
    try { await api.delete(`/offerte/${o.id}`); toast.success("Eliminata"); fetchAll(); }
    catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const openPdf = async (o, tipo = "offerta") => {
    try {
      const res = await api.get(`/offerte/${o.id}/pdf?tipo=${tipo}`, { responseType: "blob" });
      window.open(URL.createObjectURL(res.data), "_blank");
    } catch (e) { toast.error("Errore PDF"); }
  };

  const duplica = (o) => {
    setEditing(null);
    setForm({
      cliente_id: o.cliente_id,
      durata_mesi: o.durata_mesi,
      data_scadenza: inDays(30),
      note: o.note || "",
      termini_condizioni: [...(o.termini_condizioni || [])],
      righe: (o.righe || []).map(r => ({
        articolo_id: r.articolo_id, quantita: r.quantita,
        sconto_perc: r.sconto_perc, sconto_eur: r.sconto_eur,
      })),
    });
    setOpen(true);
  };

  // Preview totals (client-side only)
  const preview = (form?.righe || []).reduce((acc, r) => {
    const a = articoli.find(x => x.id === r.articolo_id);
    if (!a) return acc;
    const pu = a.prezzo_lavaggio || a.prezzo || 0;
    const pf = Math.max(0, pu * (1 - (r.sconto_perc || 0) / 100) - (r.sconto_eur || 0));
    return acc + pf * (r.quantita || 0);
  }, 0);

  return (
    <div>
      <PageHeader
        eyebrow="Commerciale"
        title="Offerte & Preventivi"
        subtitle="Genera proposte commerciali basate sul listino del cliente. Trasforma le offerte accettate in contratti con un click."
        actions={
          <Button onClick={openNew} className="bg-indaco hover:bg-indaco-dark" data-testid="new-offerta-btn">
            <Plus size={16} className="mr-1" weight="bold" />Nuova offerta
          </Button>
        }
      />

      <div className="kpi-card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Numero</th>
                <th>Cliente</th>
                <th>Durata</th>
                <th>Imponibile</th>
                <th>Scadenza</th>
                <th>Stato</th>
                <th>Azioni</th>
              </tr>
            </thead>
            <tbody>
              {list.map(o => {
                const cli = clienti.find(c => c.id === o.cliente_id);
                return (
                  <tr key={o.id} data-testid={`offerta-row-${o.id}`}>
                    <td>
                      <div className="font-mono font-bold">{o.numero}</div>
                      {o.contratto_numero && (
                        <div className="text-[11px] font-mono text-amber-700 flex items-center gap-0.5">
                          <Handshake size={11} weight="fill" />{o.contratto_numero}
                        </div>
                      )}
                    </td>
                    <td>
                      <div className="text-sm">{cli?.ragione_sociale || o.cliente_snapshot?.ragione_sociale || "—"}</div>
                      {(cli?.denominazione_struttura || o.cliente_snapshot?.denominazione_struttura) && (
                        <div className="text-[11px] text-slate-500">{cli?.denominazione_struttura || o.cliente_snapshot?.denominazione_struttura}</div>
                      )}
                    </td>
                    <td className="font-mono text-xs">{o.durata_mesi} mesi</td>
                    <td className="font-mono font-bold text-indaco">€ {o.imponibile.toFixed(2)}</td>
                    <td className="text-xs">{o.data_scadenza ? new Date(o.data_scadenza).toLocaleDateString("it-IT") : "—"}</td>
                    <td>
                      <span className={`px-2 py-0.5 text-xs rounded-full ${STATO_CLASS[o.stato] || "bg-slate-100 text-slate-600"}`}>
                        {STATO_LBL[o.stato] || o.stato}
                      </span>
                    </td>
                    <td>
                      <div className="flex items-center gap-0.5">
                        <Button variant="ghost" size="icon" onClick={() => openPdf(o, "offerta")} title="PDF Offerta" data-testid={`pdf-off-${o.id}`}><FilePdf size={14} /></Button>
                        {o.stato === "contratto" && (
                          <Button variant="ghost" size="icon" onClick={() => openPdf(o, "contratto")} title="PDF Contratto" className="text-amber-600" data-testid={`pdf-ct-${o.id}`}><FileText size={14} /></Button>
                        )}
                        <Button variant="ghost" size="icon" onClick={() => duplica(o)} title="Duplica"><Copy size={13} /></Button>
                        {o.stato !== "contratto" && (
                          <>
                            <Button variant="ghost" size="icon" onClick={() => openEdit(o)} title="Modifica"><PencilSimple size={13} /></Button>
                            {o.stato === "bozza" && (
                              <Button variant="ghost" size="icon" onClick={() => cambiaStato(o, "inviata")} title="Invia" className="text-indaco"><ArrowRight size={13} /></Button>
                            )}
                            {o.stato === "inviata" && (
                              <>
                                <Button variant="ghost" size="icon" onClick={() => cambiaStato(o, "accettata")} title="Accetta" className="text-emerald-600"><CheckCircle size={13} /></Button>
                                <Button variant="ghost" size="icon" onClick={() => cambiaStato(o, "rifiutata")} title="Rifiuta" className="text-red-600"><XCircle size={13} /></Button>
                              </>
                            )}
                            {o.stato === "accettata" && (
                              <Button variant="ghost" size="icon" onClick={() => converti(o)} title="Trasforma in contratto" className="text-amber-600" data-testid={`convert-${o.id}`}><Handshake size={14} weight="fill" /></Button>
                            )}
                            <Button variant="ghost" size="icon" onClick={() => delOff(o)} title="Elimina" className="text-red-600"><Trash size={13} /></Button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {list.length === 0 && (
                <tr><td colSpan={7} className="text-center py-16 text-slate-400">
                  <HandHeart size={32} className="mx-auto mb-2 text-slate-300" />
                  Nessuna offerta. Inizia creando la prima proposta commerciale.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Form Dialog */}
      <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setEditing(null); setForm(null); } }}>
        <DialogContent className="max-w-5xl max-h-[92vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editing ? `Modifica ${editing.numero}` : "Nuova offerta commerciale"}</DialogTitle>
          </DialogHeader>
          {form && (
            <div className="space-y-5">
              {/* Cliente + meta */}
              <section className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="md:col-span-2">
                  <Label>Cliente *</Label>
                  <Select value={form.cliente_id} onValueChange={v => setForm({...form, cliente_id: v})} disabled={!!editing}>
                    <SelectTrigger data-testid="offerta-cliente"><SelectValue placeholder="Seleziona cliente…" /></SelectTrigger>
                    <SelectContent>
                      {clienti.map(c => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}{c.listino_id && " · ⚡"}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  {selectedCliente && (
                    <div className="text-xs text-slate-500 mt-1">
                      P.IVA: <span className="font-mono">{selectedCliente.partita_iva || "—"}</span>
                      {selectedCliente.listino_id && <> · Listino cliente: <b className="text-indaco">associato</b></>}
                    </div>
                  )}
                </div>
                <div>
                  <Label>Durata contratto (mesi)</Label>
                  <Input type="number" min={1} max={120} value={form.durata_mesi} onChange={e => setForm({...form, durata_mesi: parseInt(e.target.value) || 12})} data-testid="offerta-durata" />
                </div>
                <div>
                  <Label>Scadenza proposta</Label>
                  <Input type="date" value={form.data_scadenza} onChange={e => setForm({...form, data_scadenza: e.target.value})} data-testid="offerta-scadenza" />
                </div>
                <div className="md:col-span-2">
                  <Label>Note interne</Label>
                  <Input value={form.note} onChange={e => setForm({...form, note: e.target.value})} placeholder="Opzionale" />
                </div>
              </section>

              {/* Righe articoli */}
              <section className="border border-slate-200 rounded-lg overflow-hidden">
                <div className="flex items-center justify-between px-4 py-2 bg-slate-50 border-b border-slate-200">
                  <h4 className="font-display font-bold text-sm">Articoli offerta</h4>
                  <Button type="button" variant="outline" size="sm" onClick={addRiga} data-testid="add-riga-btn"><Plus size={13} className="mr-1" />Aggiungi riga</Button>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="text-xs uppercase tracking-wide text-slate-500 bg-white border-b border-slate-200">
                      <tr><th className="p-2 text-left">Articolo</th><th>Q.tà</th><th>Sconto %</th><th>Sconto €</th><th className="text-right">Preview</th><th></th></tr>
                    </thead>
                    <tbody>
                      {form.righe.map((r, i) => {
                        const a = articoli.find(x => x.id === r.articolo_id);
                        const pu = a?.prezzo_lavaggio || a?.prezzo || 0;
                        const pf = Math.max(0, pu * (1 - (r.sconto_perc || 0) / 100) - (r.sconto_eur || 0));
                        return (
                          <tr key={i} className="border-b border-slate-100" data-testid={`riga-${i}`}>
                            <td className="p-2">
                              <Select value={r.articolo_id} onValueChange={v => updRiga(i, "articolo_id", v)}>
                                <SelectTrigger className="h-8"><SelectValue placeholder="Articolo…" /></SelectTrigger>
                                <SelectContent>
                                  {articoli.map(a => <SelectItem key={a.id} value={a.id}>{a.codice} · {a.descrizione}</SelectItem>)}
                                </SelectContent>
                              </Select>
                            </td>
                            <td><Input type="number" step="0.01" className="h-8 w-20 text-right font-mono" value={r.quantita} onChange={e => updRiga(i, "quantita", parseFloat(e.target.value) || 0)} /></td>
                            <td><Input type="number" step="0.5" min={0} max={100} className="h-8 w-16 text-right font-mono" value={r.sconto_perc} onChange={e => updRiga(i, "sconto_perc", parseFloat(e.target.value) || 0)} /></td>
                            <td><Input type="number" step="0.01" min={0} className="h-8 w-20 text-right font-mono" value={r.sconto_eur} onChange={e => updRiga(i, "sconto_eur", parseFloat(e.target.value) || 0)} /></td>
                            <td className="text-right text-xs font-mono">
                              <div className="text-slate-400 line-through">€ {pu.toFixed(2)}</div>
                              <div className="text-indaco font-bold">€ {pf.toFixed(2)}</div>
                              <div className="text-slate-700">= € {(pf * (r.quantita || 0)).toFixed(2)}</div>
                            </td>
                            <td><Button variant="ghost" size="icon" onClick={() => delRiga(i)} className="text-red-500"><Trash size={13} /></Button></td>
                          </tr>
                        );
                      })}
                      {form.righe.length === 0 && <tr><td colSpan={6} className="p-4 text-center text-slate-400 text-xs">Nessuna riga. Clicca "Aggiungi riga".</td></tr>}
                    </tbody>
                    <tfoot className="bg-indaco/5 border-t-2 border-indaco">
                      <tr>
                        <td colSpan={4} className="p-2 text-right font-semibold">Preview imponibile (verrà ricalcolato dal listino):</td>
                        <td className="text-right font-mono font-bold text-indaco">€ {preview.toFixed(2)}</td>
                        <td></td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </section>

              {/* Termini & Condizioni */}
              <section className="border border-slate-200 rounded-lg overflow-hidden">
                <div className="flex items-center justify-between px-4 py-2 bg-slate-50 border-b border-slate-200">
                  <h4 className="font-display font-bold text-sm">Termini & Condizioni</h4>
                  <div className="flex gap-1">
                    <Button type="button" variant="outline" size="sm" onClick={addTermine}><Plus size={13} className="mr-1" />Vuoto</Button>
                    {templates.length > 0 && (
                      <Select onValueChange={(tid) => { const t = templates.find(x => x.id === tid); if (t) addTemplate(t); }}>
                        <SelectTrigger className="h-9 w-48" data-testid="termini-template-select"><SelectValue placeholder="+ Template…" /></SelectTrigger>
                        <SelectContent>{templates.map(t => <SelectItem key={t.id} value={t.id}>{t.titolo}</SelectItem>)}</SelectContent>
                      </Select>
                    )}
                  </div>
                </div>
                <div className="p-3 space-y-2">
                  {form.termini_condizioni.map((t, i) => (
                    <div key={i} className="border border-slate-200 rounded p-2 bg-white" data-testid={`termine-${i}`}>
                      <div className="flex items-center gap-2 mb-1">
                        <Input value={t.titolo} onChange={e => updTermine(i, "titolo", e.target.value)} placeholder="Titolo clausola" className="h-8 text-sm font-semibold" />
                        <Button variant="ghost" size="icon" onClick={() => delTermine(i)} className="text-red-500"><Trash size={13} /></Button>
                      </div>
                      <Textarea rows={3} value={t.testo} onChange={e => updTermine(i, "testo", e.target.value)} placeholder="Testo clausola..." className="text-xs" />
                    </div>
                  ))}
                  {form.termini_condizioni.length === 0 && (
                    <div className="text-xs text-slate-400 text-center py-4">
                      Nessuna clausola. Aggiungi da template o manualmente.
                    </div>
                  )}
                </div>
              </section>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-200">
                <Button type="button" variant="outline" onClick={() => setOpen(false)}>Annulla</Button>
                <Button onClick={save} className="bg-indaco hover:bg-indaco-dark" data-testid="save-offerta-btn">
                  <FloppyDisk size={14} className="mr-1" />{editing ? "Aggiorna" : "Crea offerta"}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
