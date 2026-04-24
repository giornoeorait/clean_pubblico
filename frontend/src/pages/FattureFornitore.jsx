import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Plus, Receipt, Trash, CheckCircle, Warning } from "@phosphor-icons/react";
import { toast } from "sonner";

const RIGA_EMPTY = { descrizione: "", quantita: 1, unita_misura: "pz", prezzo_unitario: 0 };

export default function FattureFornitore() {
  const [list, setList] = useState([]);
  const [fornitori, setFornitori] = useState([]);
  const [ddtDisponibili, setDdtDisponibili] = useState([]);
  const [open, setOpen] = useState(false);
  const [filtroFornitore, setFiltroFornitore] = useState("all");
  const [filtroStato, setFiltroStato] = useState("all");
  const [form, setForm] = useState({
    fornitore_id: "", numero_fornitore: "", data: new Date().toISOString().slice(0, 10),
    data_scadenza: "", ddt_fornitore_ids: [], righe: [], iva_perc: 22, note: "",
  });
  const [modalita, setModalita] = useState("da_ddt"); // da_ddt | manuale

  const fetchAll = async () => {
    const params = [];
    if (filtroFornitore !== "all") params.push(`fornitore_id=${filtroFornitore}`);
    if (filtroStato !== "all") params.push(`stato_pagamento=${filtroStato}`);
    const [a, b] = await Promise.all([
      api.get(`/fatture-fornitore${params.length ? "?" + params.join("&") : ""}`),
      api.get("/fornitori"),
    ]);
    setList(a.data); setFornitori(b.data);
  };
  useEffect(() => { fetchAll(); }, [filtroFornitore, filtroStato]);

  useEffect(() => {
    if (form.fornitore_id && modalita === "da_ddt") {
      api.get(`/fatture-fornitore/ddt-fatturabili/${form.fornitore_id}`).then(r => setDdtDisponibili(r.data));
    } else {
      setDdtDisponibili([]);
    }
  }, [form.fornitore_id, modalita]);

  const toggleDdt = (id) => {
    const has = form.ddt_fornitore_ids.includes(id);
    setForm({ ...form, ddt_fornitore_ids: has ? form.ddt_fornitore_ids.filter(x => x !== id) : [...form.ddt_fornitore_ids, id] });
  };

  const addRigaManuale = () => setForm({ ...form, righe: [...form.righe, { ...RIGA_EMPTY }] });
  const delRiga = (i) => setForm({ ...form, righe: form.righe.filter((_, j) => j !== i) });
  const setRiga = (i, k, v) => {
    const r = [...form.righe]; r[i] = { ...r[i], [k]: v }; setForm({ ...form, righe: r });
  };

  const imponibile = modalita === "da_ddt"
    ? ddtDisponibili.filter(d => form.ddt_fornitore_ids.includes(d.id)).reduce((s, d) => s + d.totale, 0)
    : form.righe.reduce((s, r) => s + (Number(r.quantita) || 0) * (Number(r.prezzo_unitario) || 0), 0);
  const iva = imponibile * (Number(form.iva_perc) || 0) / 100;
  const totale = imponibile + iva;

  const canSave = form.fornitore_id && form.numero_fornitore && form.data &&
    (modalita === "da_ddt" ? form.ddt_fornitore_ids.length > 0 : form.righe.length > 0 && form.righe.every(r => r.descrizione && r.quantita > 0));

  const resetForm = () => {
    setForm({ fornitore_id: "", numero_fornitore: "", data: new Date().toISOString().slice(0, 10), data_scadenza: "", ddt_fornitore_ids: [], righe: [], iva_perc: 22, note: "" });
    setModalita("da_ddt");
  };

  const save = async (e) => {
    e.preventDefault();
    if (!canSave) { toast.error("Compila tutti i campi obbligatori"); return; }
    try {
      const payload = {
        fornitore_id: form.fornitore_id,
        numero_fornitore: form.numero_fornitore,
        data: form.data,
        data_scadenza: form.data_scadenza || null,
        iva_perc: Number(form.iva_perc),
        note: form.note,
        ddt_fornitore_ids: modalita === "da_ddt" ? form.ddt_fornitore_ids : [],
        righe: modalita === "manuale" ? form.righe.map(r => ({ ...r, quantita: Number(r.quantita), prezzo_unitario: Number(r.prezzo_unitario) })) : [],
      };
      await api.post("/fatture-fornitore", payload);
      toast.success("Fattura registrata");
      setOpen(false); resetForm(); fetchAll();
    } catch (e2) { toast.error(e2.response?.data?.detail || "Errore"); }
  };

  const paga = async (id) => {
    if (!window.confirm("Contrassegnare come pagata?")) return;
    try { await api.patch(`/fatture-fornitore/${id}/paga`); toast.success("Marcata pagata"); fetchAll(); }
    catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };
  const del = async (id) => {
    if (!window.confirm("Eliminare fattura? I DDT collegati torneranno fatturabili.")) return;
    try { await api.delete(`/fatture-fornitore/${id}`); toast.success("Eliminata"); fetchAll(); }
    catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Ciclo acquisti"
        title="Fatture fornitore"
        subtitle="Fatture passive registrate. Genera da DDT ricevuti oppure inserisci righe manualmente (es. utenze, servizi)."
        actions={
          <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) resetForm(); }}>
            <DialogTrigger asChild>
              <Button className="bg-indaco hover:bg-indaco-dark" data-testid="new-ft-forn-btn"><Plus size={16} weight="bold" className="mr-1" /> Nuova Fattura</Button>
            </DialogTrigger>
            <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
              <DialogHeader><DialogTitle>Nuova fattura fornitore</DialogTitle></DialogHeader>
              <form onSubmit={save} className="space-y-4">
                <div className="grid grid-cols-3 gap-3">
                  <div className="col-span-3">
                    <Label>Fornitore *</Label>
                    <Select value={form.fornitore_id} onValueChange={v => setForm({ ...form, fornitore_id: v, ddt_fornitore_ids: [] })}>
                      <SelectTrigger data-testid="ft-forn-select"><SelectValue placeholder="Seleziona fornitore" /></SelectTrigger>
                      <SelectContent>{fornitori.map(f => <SelectItem key={f.id} value={f.id}>{f.ragione_sociale}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <div><Label>Numero fornitore *</Label><Input value={form.numero_fornitore} onChange={e => setForm({ ...form, numero_fornitore: e.target.value })} placeholder="FT-2026-001" data-testid="ft-forn-numero" /></div>
                  <div><Label>Data *</Label><Input type="date" value={form.data} onChange={e => setForm({ ...form, data: e.target.value })} /></div>
                  <div><Label>Scadenza</Label><Input type="date" value={form.data_scadenza} onChange={e => setForm({ ...form, data_scadenza: e.target.value })} /></div>
                </div>

                <div className="flex gap-2">
                  <button type="button" onClick={() => setModalita("da_ddt")} className={`flex-1 border rounded-lg p-3 text-sm transition ${modalita === "da_ddt" ? "border-indaco bg-indaco/5 text-indaco font-bold" : "border-slate-200 hover:border-slate-300"}`}>
                    Da DDT ricevuti
                  </button>
                  <button type="button" onClick={() => setModalita("manuale")} className={`flex-1 border rounded-lg p-3 text-sm transition ${modalita === "manuale" ? "border-indaco bg-indaco/5 text-indaco font-bold" : "border-slate-200 hover:border-slate-300"}`}>
                    Righe manuali (utenze/servizi)
                  </button>
                </div>

                {modalita === "da_ddt" && (
                  <div className="border rounded-lg p-3 bg-slate-50/40">
                    <h4 className="font-display font-bold text-sm mb-2">DDT fatturabili</h4>
                    {!form.fornitore_id && <p className="text-xs text-slate-400">Seleziona un fornitore</p>}
                    {form.fornitore_id && ddtDisponibili.length === 0 && <p className="text-xs text-slate-400">Nessun DDT da fatturare</p>}
                    <div className="space-y-1">
                      {ddtDisponibili.map(d => (
                        <label key={d.id} className="flex items-center gap-2 p-2 border rounded hover:bg-white cursor-pointer">
                          <input type="checkbox" checked={form.ddt_fornitore_ids.includes(d.id)} onChange={() => toggleDdt(d.id)} data-testid={`ddt-chk-${d.id}`} />
                          <span className="font-mono text-xs">{d.numero}</span>
                          <span className="text-xs text-slate-500">rif. {d.numero_fornitore}</span>
                          <span className="text-xs ml-auto font-mono">€ {d.totale.toFixed(2)}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                )}

                {modalita === "manuale" && (
                  <div className="border rounded-lg p-3 bg-slate-50/40">
                    <div className="flex justify-between mb-2">
                      <h4 className="font-display font-bold text-sm">Righe manuali</h4>
                      <Button type="button" size="sm" variant="outline" onClick={addRigaManuale}><Plus size={14} className="mr-1" />Aggiungi</Button>
                    </div>
                    <div className="space-y-2">
                      {form.righe.map((r, i) => (
                        <div key={i} className="grid grid-cols-12 gap-2 items-end">
                          <div className="col-span-5"><Input value={r.descrizione} onChange={e => setRiga(i, "descrizione", e.target.value)} placeholder="Descrizione" /></div>
                          <div className="col-span-2"><Input type="number" step="0.01" value={r.quantita} onChange={e => setRiga(i, "quantita", e.target.value)} placeholder="Qtà" /></div>
                          <div className="col-span-1"><Input value={r.unita_misura} onChange={e => setRiga(i, "unita_misura", e.target.value)} /></div>
                          <div className="col-span-2"><Input type="number" step="0.01" value={r.prezzo_unitario} onChange={e => setRiga(i, "prezzo_unitario", e.target.value)} placeholder="€ unit." /></div>
                          <div className="col-span-1 text-right text-xs font-mono pb-2">€ {((Number(r.quantita) || 0) * (Number(r.prezzo_unitario) || 0)).toFixed(2)}</div>
                          <div className="col-span-1 pb-1"><button type="button" onClick={() => delRiga(i)} className="p-1.5 hover:bg-red-50 rounded"><Trash size={14} className="text-red-500" /></button></div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-4 gap-3 items-end">
                  <div><Label>IVA %</Label><Input type="number" step="0.01" value={form.iva_perc} onChange={e => setForm({ ...form, iva_perc: e.target.value })} /></div>
                  <div className="col-span-3 flex justify-end gap-6 pr-2 pb-1 text-sm">
                    <div className="text-right"><div className="text-[11px] uppercase text-slate-500">Imponibile</div><div className="font-mono font-bold">€ {imponibile.toFixed(2)}</div></div>
                    <div className="text-right"><div className="text-[11px] uppercase text-slate-500">IVA</div><div className="font-mono">€ {iva.toFixed(2)}</div></div>
                    <div className="text-right"><div className="text-[11px] uppercase text-slate-500">Totale</div><div className="font-mono font-bold text-indaco text-lg">€ {totale.toFixed(2)}</div></div>
                  </div>
                </div>

                <div><Label>Note</Label><Input value={form.note} onChange={e => setForm({ ...form, note: e.target.value })} /></div>

                {!canSave && <div className="flex items-center gap-2 text-sm text-amber-700 bg-amber-50 rounded px-3 py-2"><Warning size={16} weight="fill" />Compila fornitore, numero, data e almeno {modalita === "da_ddt" ? "un DDT" : "una riga"}.</div>}

                <div className="flex justify-end gap-2">
                  <Button type="button" variant="outline" onClick={() => setOpen(false)}>Annulla</Button>
                  <Button type="submit" disabled={!canSave} className="bg-indaco hover:bg-indaco-dark" data-testid="save-ft-forn-btn">Salva fattura</Button>
                </div>
              </form>
            </DialogContent>
          </Dialog>
        }
      />

      <div className="kpi-card mb-6 flex gap-3 flex-wrap">
        <Select value={filtroFornitore} onValueChange={setFiltroFornitore}>
          <SelectTrigger className="w-64"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tutti i fornitori</SelectItem>
            {fornitori.map(f => <SelectItem key={f.id} value={f.id}>{f.ragione_sociale}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={filtroStato} onValueChange={setFiltroStato}>
          <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tutti gli stati</SelectItem>
            <SelectItem value="da_pagare">Da pagare</SelectItem>
            <SelectItem value="pagata">Pagate</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="kpi-card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead><tr><th>Numero int.</th><th>Fornitore</th><th>Rif. fornitore</th><th>Data</th><th>Scadenza</th><th>Totale</th><th>Stato</th><th>Azioni</th></tr></thead>
            <tbody>
              {list.map(f => {
                const forn = fornitori.find(x => x.id === f.fornitore_id);
                return (
                  <tr key={f.id} data-testid={`ftforn-row-${f.id}`}>
                    <td className="font-mono text-xs">{f.numero}</td>
                    <td><div className="flex items-center gap-2"><Receipt size={14} className="text-amber-700" />{forn?.ragione_sociale || "—"}</div></td>
                    <td className="text-xs font-mono">{f.numero_fornitore}</td>
                    <td className="text-xs">{f.data}</td>
                    <td className="text-xs">{f.data_scadenza || "—"}</td>
                    <td className="text-right font-mono font-bold">€ {f.totale.toFixed(2)}</td>
                    <td><span className={`px-2 py-0.5 text-xs rounded-full ${f.stato_pagamento === "pagata" ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}>{f.stato_pagamento}</span></td>
                    <td>
                      <div className="flex gap-1">
                        {f.stato_pagamento === "da_pagare" && <button onClick={() => paga(f.id)} className="p-1.5 hover:bg-emerald-50 rounded" title="Paga" data-testid={`ftforn-paga-${f.id}`}><CheckCircle size={14} className="text-emerald-600" /></button>}
                        <button onClick={() => del(f.id)} className="p-1.5 hover:bg-red-50 rounded" data-testid={`ftforn-del-${f.id}`}><Trash size={14} className="text-red-500" /></button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {list.length === 0 && <tr><td colSpan={8} className="text-center py-8 text-slate-400">Nessuna fattura.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
