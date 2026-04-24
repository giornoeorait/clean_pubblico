import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Plus, PencilSimple, Trash, Truck, CheckCircle, XCircle } from "@phosphor-icons/react";
import { toast } from "sonner";

const EMPTY = {
  targa: "", marca_modello: "", anno: "", alimentazione: "gasolio",
  km_attuali: 0, note: "", attivo: true,
};

const ALIMENTAZIONI = ["gasolio", "benzina", "elettrico", "ibrido", "gpl", "metano"];

export default function Automezzi() {
  const [list, setList] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);

  const fetchList = async () => { const { data } = await api.get("/automezzi"); setList(data); };
  useEffect(() => { fetchList(); }, []);

  const save = async (e) => {
    e.preventDefault();
    if (!form.targa.trim()) { toast.error("Targa obbligatoria"); return; }
    try {
      const payload = { ...form, km_attuali: Number(form.km_attuali) || 0, anno: form.anno ? Number(form.anno) : null };
      if (editing) { await api.patch(`/automezzi/${editing}`, payload); toast.success("Aggiornato"); }
      else { await api.post("/automezzi", payload); toast.success("Creato"); }
      setOpen(false); setEditing(null); setForm(EMPTY); fetchList();
    } catch (e2) { toast.error(e2.response?.data?.detail || "Errore"); }
  };

  const edit = (a) => { setForm({ ...EMPTY, ...a, anno: a.anno || "", km_attuali: a.km_attuali || 0 }); setEditing(a.id); setOpen(true); };
  const del = async (id) => {
    if (!window.confirm("Eliminare automezzo? (i costi già registrati restano)")) return;
    try { await api.delete(`/automezzi/${id}`); toast.success("Eliminato"); fetchList(); }
    catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };
  const toggleAttivo = async (a) => {
    try { await api.patch(`/automezzi/${a.id}`, { attivo: !a.attivo }); fetchList(); }
    catch { toast.error("Errore"); }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Controllo di gestione"
        title="Automezzi"
        subtitle="Parco veicoli aziendale. Le targhe qui censite sono selezionabili dai costi automezzi."
        actions={
          <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setEditing(null); setForm(EMPTY); } }}>
            <DialogTrigger asChild>
              <Button className="bg-indaco hover:bg-indaco-dark" data-testid="new-auto-btn"><Plus size={16} className="mr-1" /> Nuovo automezzo</Button>
            </DialogTrigger>
            <DialogContent className="max-w-xl">
              <DialogHeader><DialogTitle>{editing ? "Modifica automezzo" : "Nuovo automezzo"}</DialogTitle><DialogDescription>Anagrafica veicolo. La targa è univoca per azienda.</DialogDescription></DialogHeader>
              <form onSubmit={save} className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div><Label>Targa *</Label><Input value={form.targa} onChange={e => setForm({ ...form, targa: e.target.value.toUpperCase() })} placeholder="AB123CD" data-testid="auto-targa" /></div>
                  <div><Label>Marca e modello</Label><Input value={form.marca_modello} onChange={e => setForm({ ...form, marca_modello: e.target.value })} placeholder="Fiat Ducato" /></div>
                  <div><Label>Anno</Label><Input type="number" value={form.anno} onChange={e => setForm({ ...form, anno: e.target.value })} placeholder="2022" /></div>
                  <div>
                    <Label>Alimentazione</Label>
                    <Select value={form.alimentazione} onValueChange={v => setForm({ ...form, alimentazione: v })}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>{ALIMENTAZIONI.map(a => <SelectItem key={a} value={a}>{a}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <div className="col-span-2"><Label>Km attuali</Label><Input type="number" step="0.1" value={form.km_attuali} onChange={e => setForm({ ...form, km_attuali: e.target.value })} /></div>
                  <div className="col-span-2"><Label>Note</Label><Input value={form.note} onChange={e => setForm({ ...form, note: e.target.value })} /></div>
                </div>
                <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setOpen(false)}>Annulla</Button><Button type="submit" className="bg-indaco hover:bg-indaco-dark" data-testid="save-auto-btn">Salva</Button></div>
              </form>
            </DialogContent>
          </Dialog>
        }
      />

      <div className="kpi-card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead><tr><th>Targa</th><th>Marca/modello</th><th>Anno</th><th>Alimentazione</th><th>Km attuali</th><th>Attivo</th><th>Azioni</th></tr></thead>
            <tbody>
              {list.map(a => (
                <tr key={a.id} data-testid={`auto-row-${a.id}`}>
                  <td className="font-mono font-bold"><div className="flex items-center gap-2"><Truck size={14} className="text-amber-700" />{a.targa}</div></td>
                  <td>{a.marca_modello || "—"}</td>
                  <td className="text-xs">{a.anno || "—"}</td>
                  <td><span className="px-2 py-0.5 rounded-full text-xs bg-amber-50 text-amber-700">{a.alimentazione || "—"}</span></td>
                  <td className="text-right font-mono">{(a.km_attuali || 0).toFixed(0)} km</td>
                  <td>
                    <button onClick={() => toggleAttivo(a)} title="Toggle attivo" className="p-1 hover:bg-slate-50 rounded">
                      {a.attivo ? <CheckCircle size={16} className="text-emerald-500" weight="fill" /> : <XCircle size={16} className="text-slate-400" />}
                    </button>
                  </td>
                  <td><div className="flex gap-1">
                    <button onClick={() => edit(a)} className="p-1.5 hover:bg-slate-100 rounded" data-testid={`auto-edit-${a.id}`}><PencilSimple size={14} /></button>
                    <button onClick={() => del(a.id)} className="p-1.5 hover:bg-red-50 rounded" data-testid={`auto-del-${a.id}`}><Trash size={14} className="text-red-500" /></button>
                  </div></td>
                </tr>
              ))}
              {list.length === 0 && <tr><td colSpan={7} className="text-center py-8 text-slate-400">Nessun automezzo. Crea il primo!</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
