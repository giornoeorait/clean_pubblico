import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Plus, PencilSimple, Trash, User, CheckCircle, XCircle, Lightning } from "@phosphor-icons/react";
import { toast } from "sonner";

const EMPTY = {
  nome: "", codice_fiscale: "", ruolo: "", email: "", telefono: "",
  data_assunzione: "", tipo_contratto: "indeterminato",
  stipendio_mensile: 0, ore_contrattuali: 160, note: "", attivo: true,
};

const CONTRATTI = ["indeterminato", "determinato", "apprendistato", "collaborazione"];

export default function Dipendenti() {
  const [list, setList] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [genOpen, setGenOpen] = useState(false);
  const [mese, setMese] = useState(new Date().toISOString().slice(0, 7));

  const fetchList = async () => {
    const { data } = await api.get("/dipendenti");
    setList(data);
  };
  useEffect(() => { fetchList(); }, []);

  const save = async (e) => {
    e.preventDefault();
    if (!form.nome.trim()) { toast.error("Nome obbligatorio"); return; }
    try {
      const payload = { ...form, stipendio_mensile: Number(form.stipendio_mensile), ore_contrattuali: Number(form.ore_contrattuali) || null };
      if (!payload.data_assunzione) delete payload.data_assunzione;
      if (editing) { await api.patch(`/dipendenti/${editing}`, payload); toast.success("Aggiornato"); }
      else { await api.post("/dipendenti", payload); toast.success("Creato"); }
      setOpen(false); setEditing(null); setForm(EMPTY); fetchList();
    } catch (e2) { toast.error(e2.response?.data?.detail || "Errore"); }
  };

  const edit = (d) => { setForm({ ...EMPTY, ...d, stipendio_mensile: d.stipendio_mensile || 0, ore_contrattuali: d.ore_contrattuali ?? 160, data_assunzione: d.data_assunzione || "" }); setEditing(d.id); setOpen(true); };
  const del = async (id) => {
    if (!window.confirm("Eliminare dipendente? (i costi già registrati restano)")) return;
    try { await api.delete(`/dipendenti/${id}`); toast.success("Eliminato"); fetchList(); }
    catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };
  const toggleAttivo = async (d) => {
    try { await api.patch(`/dipendenti/${d.id}`, { attivo: !d.attivo }); fetchList(); }
    catch { toast.error("Errore"); }
  };

  const generaStipendi = async () => {
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(mese)) { toast.error("Formato yyyy-mm"); return; }
    try {
      const { data } = await api.post("/dipendenti/genera-stipendi", { mese_riferimento: mese });
      toast.success(`${data.n_creati} stipendi creati · ${data.n_skippati} già esistenti`);
      setGenOpen(false);
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Controllo di gestione"
        title="Dipendenti"
        subtitle="Anagrafica personale con stipendi mensili. Genera automaticamente i costi personale ogni mese."
        actions={
          <div className="flex gap-2">
            <Dialog open={genOpen} onOpenChange={setGenOpen}>
              <DialogTrigger asChild>
                <Button variant="outline" data-testid="genera-stipendi-btn"><Lightning size={16} className="mr-1" /> Genera stipendi</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader><DialogTitle>Genera stipendi mese</DialogTitle><DialogDescription>Crea voci costo personale per tutti i dipendenti attivi. Operazione idempotente.</DialogDescription></DialogHeader>
                <div className="space-y-3">
                  <div><Label>Mese di riferimento (yyyy-mm)</Label><Input value={mese} onChange={e => setMese(e.target.value)} placeholder="2026-05" data-testid="mese-stipendi" /></div>
                  <p className="text-xs text-slate-500">Saranno generati i costi per i <b>{list.filter(d => d.attivo && d.stipendio_mensile > 0).length}</b> dipendenti attivi con stipendio &gt; 0. I duplicati verranno saltati.</p>
                </div>
                <div className="flex justify-end gap-2"><Button variant="outline" onClick={() => setGenOpen(false)}>Annulla</Button><Button onClick={generaStipendi} className="bg-indaco hover:bg-indaco-dark" data-testid="conferma-gen-stipendi">Genera</Button></div>
              </DialogContent>
            </Dialog>
            <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setEditing(null); setForm(EMPTY); } }}>
              <DialogTrigger asChild>
                <Button className="bg-indaco hover:bg-indaco-dark" data-testid="new-dip-btn"><Plus size={16} className="mr-1" /> Nuovo dipendente</Button>
              </DialogTrigger>
              <DialogContent className="max-w-2xl">
                <DialogHeader><DialogTitle>{editing ? "Modifica dipendente" : "Nuovo dipendente"}</DialogTitle><DialogDescription>Compila anagrafica e contratto. Il campo stipendio mensile alimenta la generazione automatica costi.</DialogDescription></DialogHeader>
                <form onSubmit={save} className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="col-span-2"><Label>Nome e cognome *</Label><Input value={form.nome} onChange={e => setForm({ ...form, nome: e.target.value })} data-testid="dip-nome" /></div>
                    <div><Label>Codice fiscale</Label><Input value={form.codice_fiscale} onChange={e => setForm({ ...form, codice_fiscale: e.target.value })} /></div>
                    <div><Label>Ruolo</Label><Input value={form.ruolo} onChange={e => setForm({ ...form, ruolo: e.target.value })} placeholder="Operatore, Autista..." /></div>
                    <div><Label>Email</Label><Input type="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} /></div>
                    <div><Label>Telefono</Label><Input value={form.telefono} onChange={e => setForm({ ...form, telefono: e.target.value })} /></div>
                    <div><Label>Data assunzione</Label><Input type="date" value={form.data_assunzione} onChange={e => setForm({ ...form, data_assunzione: e.target.value })} /></div>
                    <div>
                      <Label>Tipo contratto</Label>
                      <Select value={form.tipo_contratto} onValueChange={v => setForm({ ...form, tipo_contratto: v })}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>{CONTRATTI.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                      </Select>
                    </div>
                    <div><Label>Stipendio mensile lordo €</Label><Input type="number" step="0.01" value={form.stipendio_mensile} onChange={e => setForm({ ...form, stipendio_mensile: e.target.value })} data-testid="dip-stipendio" /></div>
                    <div><Label>Ore contrattuali/mese</Label><Input type="number" step="0.5" value={form.ore_contrattuali} onChange={e => setForm({ ...form, ore_contrattuali: e.target.value })} /></div>
                  </div>
                  <div><Label>Note</Label><Input value={form.note} onChange={e => setForm({ ...form, note: e.target.value })} /></div>
                  <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setOpen(false)}>Annulla</Button><Button type="submit" className="bg-indaco hover:bg-indaco-dark" data-testid="save-dip-btn">Salva</Button></div>
                </form>
              </DialogContent>
            </Dialog>
          </div>
        }
      />

      <div className="kpi-card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead><tr><th>Nome</th><th>Ruolo</th><th>Contratto</th><th>Stipendio</th><th>Ore</th><th>Dal</th><th>Attivo</th><th>Azioni</th></tr></thead>
            <tbody>
              {list.map(d => (
                <tr key={d.id} data-testid={`dip-row-${d.id}`}>
                  <td><div className="flex items-center gap-2"><User size={14} className="text-violet-700" />{d.nome}</div>{d.ruolo && <div className="text-[11px] text-slate-500">{d.ruolo}</div>}</td>
                  <td className="text-xs">{d.ruolo || "—"}</td>
                  <td><span className="px-2 py-0.5 rounded-full text-xs bg-violet-50 text-violet-700">{d.tipo_contratto}</span></td>
                  <td className="font-mono font-bold">€ {(d.stipendio_mensile || 0).toFixed(2)}</td>
                  <td className="text-xs">{d.ore_contrattuali || "—"}</td>
                  <td className="text-xs">{d.data_assunzione || "—"}</td>
                  <td>
                    <button onClick={() => toggleAttivo(d)} title="Toggle attivo" className="p-1 hover:bg-slate-50 rounded">
                      {d.attivo ? <CheckCircle size={16} className="text-emerald-500" weight="fill" /> : <XCircle size={16} className="text-slate-400" />}
                    </button>
                  </td>
                  <td><div className="flex gap-1">
                    <button onClick={() => edit(d)} className="p-1.5 hover:bg-slate-100 rounded" data-testid={`dip-edit-${d.id}`}><PencilSimple size={14} /></button>
                    <button onClick={() => del(d.id)} className="p-1.5 hover:bg-red-50 rounded" data-testid={`dip-del-${d.id}`}><Trash size={14} className="text-red-500" /></button>
                  </div></td>
                </tr>
              ))}
              {list.length === 0 && <tr><td colSpan={8} className="text-center py-8 text-slate-400">Nessun dipendente. Crea il primo!</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
