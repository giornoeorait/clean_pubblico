import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Plus, Truck, Trash, PencilSimple, Warning } from "@phosphor-icons/react";
import { toast } from "sonner";

const RIGA_EMPTY = { descrizione: "", quantita: 1, unita_misura: "pz", prezzo_unitario: 0 };

export default function DdtFornitore() {
  const [list, setList] = useState([]);
  const [fornitori, setFornitori] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({
    fornitore_id: "", numero_fornitore: "", data: new Date().toISOString().slice(0, 10),
    righe: [{ ...RIGA_EMPTY }], note: "",
  });
  const [fornitoreFilter, setFornitoreFilter] = useState("all");

  const fetchAll = async () => {
    const q = fornitoreFilter !== "all" ? `?fornitore_id=${fornitoreFilter}` : "";
    const [a, b] = await Promise.all([
      api.get(`/ddt-fornitore${q}`),
      api.get(`/fornitori`),
    ]);
    setList(a.data); setFornitori(b.data);
  };
  useEffect(() => { fetchAll(); }, [fornitoreFilter]);

  const addRiga = () => setForm({ ...form, righe: [...form.righe, { ...RIGA_EMPTY }] });
  const delRiga = (i) => setForm({ ...form, righe: form.righe.filter((_, j) => j !== i) });
  const setRiga = (i, k, v) => {
    const r = [...form.righe]; r[i] = { ...r[i], [k]: v }; setForm({ ...form, righe: r });
  };

  const totale = form.righe.reduce((s, r) => s + (Number(r.quantita) || 0) * (Number(r.prezzo_unitario) || 0), 0);

  const canSave = form.fornitore_id && form.numero_fornitore && form.data && form.righe.length > 0 && form.righe.every(r => r.descrizione && r.quantita > 0);

  const save = async (e) => {
    e.preventDefault();
    if (!canSave) { toast.error("Compila tutti i campi obbligatori"); return; }
    try {
      const payload = { ...form, righe: form.righe.map(r => ({ ...r, quantita: Number(r.quantita), prezzo_unitario: Number(r.prezzo_unitario) })) };
      if (editing) { await api.patch(`/ddt-fornitore/${editing}`, { numero_fornitore: payload.numero_fornitore, data: payload.data, righe: payload.righe, note: payload.note }); toast.success("DDT aggiornato"); }
      else { await api.post("/ddt-fornitore", payload); toast.success("DDT creato"); }
      setOpen(false); setEditing(null); resetForm(); fetchAll();
    } catch (e2) { toast.error(e2.response?.data?.detail || "Errore"); }
  };

  const resetForm = () => setForm({ fornitore_id: "", numero_fornitore: "", data: new Date().toISOString().slice(0, 10), righe: [{ ...RIGA_EMPTY }], note: "" });

  const edit = (d) => {
    setForm({
      fornitore_id: d.fornitore_id,
      numero_fornitore: d.numero_fornitore,
      data: d.data,
      righe: d.righe.map(r => ({ descrizione: r.descrizione, quantita: r.quantita, unita_misura: r.unita_misura, prezzo_unitario: r.prezzo_unitario })),
      note: d.note || "",
    });
    setEditing(d.id); setOpen(true);
  };
  const del = async (id) => {
    if (!window.confirm("Eliminare DDT?")) return;
    try { await api.delete(`/ddt-fornitore/${id}`); toast.success("Eliminato"); fetchAll(); }
    catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Ciclo acquisti"
        title="DDT ricevuti"
        subtitle="Registra i documenti di trasporto ricevuti dai fornitori. Ogni DDT può poi essere incluso in una fattura passiva."
        actions={
          <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setEditing(null); resetForm(); } }}>
            <DialogTrigger asChild>
              <Button className="bg-indaco hover:bg-indaco-dark" data-testid="new-ddt-forn-btn"><Plus size={16} weight="bold" className="mr-1" /> Nuovo DDT</Button>
            </DialogTrigger>
            <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
              <DialogHeader><DialogTitle>{editing ? "Modifica DDT fornitore" : "Nuovo DDT fornitore"}</DialogTitle></DialogHeader>
              <form onSubmit={save} className="space-y-4">
                <div className="grid grid-cols-3 gap-3">
                  <div className="col-span-2">
                    <Label>Fornitore *</Label>
                    <Select value={form.fornitore_id} onValueChange={v => setForm({ ...form, fornitore_id: v })} disabled={!!editing}>
                      <SelectTrigger data-testid="ddt-forn-select"><SelectValue placeholder="Seleziona fornitore" /></SelectTrigger>
                      <SelectContent>{fornitori.map(f => <SelectItem key={f.id} value={f.id}>{f.ragione_sociale}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <div><Label>Data *</Label><Input type="date" value={form.data} onChange={e => setForm({ ...form, data: e.target.value })} /></div>
                  <div className="col-span-3"><Label>Numero DDT fornitore *</Label><Input value={form.numero_fornitore} onChange={e => setForm({ ...form, numero_fornitore: e.target.value })} placeholder="Es. DDT-FORN-2026-001" data-testid="ddt-forn-numero" /></div>
                </div>

                <div className="border rounded-lg p-3 bg-slate-50/40">
                  <div className="flex justify-between items-center mb-2">
                    <h4 className="font-display font-bold text-sm">Righe</h4>
                    <Button type="button" size="sm" variant="outline" onClick={addRiga}><Plus size={14} className="mr-1" />Aggiungi</Button>
                  </div>
                  <div className="space-y-2">
                    {form.righe.map((r, i) => (
                      <div key={i} className="grid grid-cols-12 gap-2 items-end">
                        <div className="col-span-5"><Label className="text-[11px]">Descrizione</Label><Input value={r.descrizione} onChange={e => setRiga(i, "descrizione", e.target.value)} /></div>
                        <div className="col-span-2"><Label className="text-[11px]">Qtà</Label><Input type="number" step="0.01" value={r.quantita} onChange={e => setRiga(i, "quantita", e.target.value)} /></div>
                        <div className="col-span-1"><Label className="text-[11px]">UM</Label><Input value={r.unita_misura} onChange={e => setRiga(i, "unita_misura", e.target.value)} /></div>
                        <div className="col-span-2"><Label className="text-[11px]">€ unit.</Label><Input type="number" step="0.01" value={r.prezzo_unitario} onChange={e => setRiga(i, "prezzo_unitario", e.target.value)} /></div>
                        <div className="col-span-1 text-right text-xs font-mono pb-2">€ {((Number(r.quantita) || 0) * (Number(r.prezzo_unitario) || 0)).toFixed(2)}</div>
                        <div className="col-span-1 pb-1"><button type="button" onClick={() => delRiga(i)} className="p-1.5 hover:bg-red-50 rounded"><Trash size={14} className="text-red-500" /></button></div>
                      </div>
                    ))}
                  </div>
                  <div className="flex justify-end mt-3 pt-3 border-t">
                    <div className="text-right"><div className="text-[11px] uppercase text-slate-500">Totale imponibile</div><div className="text-xl font-display font-bold text-indaco">€ {totale.toFixed(2)}</div></div>
                  </div>
                </div>

                <div><Label>Note</Label><Input value={form.note} onChange={e => setForm({ ...form, note: e.target.value })} /></div>

                {!canSave && <div className="flex items-center gap-2 text-sm text-amber-700 bg-amber-50 rounded px-3 py-2"><Warning size={16} weight="fill" />Compila fornitore, numero, data e almeno una riga con descrizione.</div>}

                <div className="flex justify-end gap-2">
                  <Button type="button" variant="outline" onClick={() => setOpen(false)}>Annulla</Button>
                  <Button type="submit" disabled={!canSave} className="bg-indaco hover:bg-indaco-dark" data-testid="save-ddt-forn-btn">Salva DDT</Button>
                </div>
              </form>
            </DialogContent>
          </Dialog>
        }
      />

      <div className="kpi-card mb-6">
        <Select value={fornitoreFilter} onValueChange={setFornitoreFilter}>
          <SelectTrigger className="w-full md:w-80"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tutti i fornitori</SelectItem>
            {fornitori.map(f => <SelectItem key={f.id} value={f.id}>{f.ragione_sociale}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      <div className="kpi-card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead><tr><th>Numero int.</th><th>Fornitore</th><th>Rif. fornitore</th><th>Data</th><th>Righe</th><th>Totale</th><th>Stato</th><th>Azioni</th></tr></thead>
            <tbody>
              {list.map(d => {
                const f = fornitori.find(x => x.id === d.fornitore_id);
                return (
                  <tr key={d.id} data-testid={`ddtforn-row-${d.id}`}>
                    <td className="font-mono text-xs">{d.numero}</td>
                    <td><div className="flex items-center gap-2"><Truck size={14} className="text-amber-700" />{f?.ragione_sociale || "—"}</div></td>
                    <td className="text-xs font-mono">{d.numero_fornitore}</td>
                    <td className="text-xs">{d.data}</td>
                    <td className="text-xs">{d.righe.length}</td>
                    <td className="text-right font-mono">€ {d.totale.toFixed(2)}</td>
                    <td><span className={`px-2 py-0.5 text-xs rounded-full ${d.stato_fatturazione === "fatturato" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>{d.stato_fatturazione === "fatturato" ? `→ ${d.fattura_fornitore_numero}` : "da fatturare"}</span></td>
                    <td>
                      <div className="flex gap-1">
                        {d.stato_fatturazione !== "fatturato" && <button onClick={() => edit(d)} className="p-1.5 hover:bg-slate-100 rounded" data-testid={`ddtforn-edit-${d.id}`}><PencilSimple size={14} /></button>}
                        {d.stato_fatturazione !== "fatturato" && <button onClick={() => del(d.id)} className="p-1.5 hover:bg-red-50 rounded" data-testid={`ddtforn-del-${d.id}`}><Trash size={14} className="text-red-500" /></button>}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {list.length === 0 && <tr><td colSpan={8} className="text-center py-8 text-slate-400">Nessun DDT ricevuto.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
