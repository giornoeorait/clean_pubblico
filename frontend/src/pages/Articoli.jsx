import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Plus, Package, Barcode, PencilSimple, Trash } from "@phosphor-icons/react";
import { toast } from "sonner";

const EMPTY = { codice: "", descrizione: "", categoria: "biancheria", tipo: "capo", materiale: "", lavaggio: "standard", temperatura: 60, barcode: "", peso_medio: 0.5, prezzo: 0, prezzo_tipo: "capo" };

export default function Articoli() {
  const [list, setList] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [editing, setEditing] = useState(null);

  const fetch = async () => { const { data } = await api.get("/articoli"); setList(data); };
  useEffect(() => { fetch(); }, []);

  const save = async (e) => {
    e.preventDefault();
    try {
      if (editing) await api.patch(`/articoli/${editing}`, form);
      else await api.post("/articoli", form);
      toast.success("Salvato"); setOpen(false); setEditing(null); setForm(EMPTY); fetch();
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const edit = (x) => { setForm({ ...EMPTY, ...x }); setEditing(x.id); setOpen(true); };
  const del = async (id) => { if (!window.confirm("Eliminare?")) return; await api.delete(`/articoli/${id}`); toast.success("Eliminato"); fetch(); };

  return (
    <div>
      <PageHeader
        eyebrow="Anagrafica"
        title="Articoli"
        subtitle="Capi singoli, tovagliato a peso e kit. Prezzi per capo, kg o canone."
        actions={
          <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setEditing(null); setForm(EMPTY); }}}>
            <DialogTrigger asChild><Button className="bg-indaco hover:bg-indaco-dark" data-testid="new-articolo-btn"><Plus size={16} weight="bold" className="mr-1" />Nuovo Articolo</Button></DialogTrigger>
            <DialogContent className="max-w-2xl">
              <DialogHeader><DialogTitle>{editing ? "Modifica articolo" : "Nuovo articolo"}</DialogTitle></DialogHeader>
              <form onSubmit={save} className="grid grid-cols-2 gap-4">
                <div><Label>Codice *</Label><Input required value={form.codice} onChange={e => setForm({...form, codice: e.target.value})} /></div>
                <div><Label>Barcode</Label><Input value={form.barcode} onChange={e => setForm({...form, barcode: e.target.value})} /></div>
                <div className="col-span-2"><Label>Descrizione *</Label><Input required value={form.descrizione} onChange={e => setForm({...form, descrizione: e.target.value})} /></div>
                <div><Label>Categoria</Label><Input value={form.categoria} onChange={e => setForm({...form, categoria: e.target.value})} /></div>
                <div>
                  <Label>Tipo</Label>
                  <Select value={form.tipo} onValueChange={v => setForm({...form, tipo: v})}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="capo">Capo singolo</SelectItem>
                      <SelectItem value="lotto_peso">Lotto a peso</SelectItem>
                      <SelectItem value="kit">Kit</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div><Label>Materiale</Label><Input value={form.materiale} onChange={e => setForm({...form, materiale: e.target.value})} /></div>
                <div><Label>Lavaggio</Label><Input value={form.lavaggio} onChange={e => setForm({...form, lavaggio: e.target.value})} /></div>
                <div><Label>Temperatura (°C)</Label><Input type="number" value={form.temperatura} onChange={e => setForm({...form, temperatura: parseInt(e.target.value)})} /></div>
                <div><Label>Peso medio (kg)</Label><Input type="number" step="0.1" value={form.peso_medio} onChange={e => setForm({...form, peso_medio: parseFloat(e.target.value)})} /></div>
                <div><Label>Prezzo (€)</Label><Input type="number" step="0.01" value={form.prezzo} onChange={e => setForm({...form, prezzo: parseFloat(e.target.value)})} /></div>
                <div>
                  <Label>Tipo prezzo</Label>
                  <Select value={form.prezzo_tipo} onValueChange={v => setForm({...form, prezzo_tipo: v})}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="capo">A capo</SelectItem>
                      <SelectItem value="kg">A kg</SelectItem>
                      <SelectItem value="canone">Canone</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="col-span-2 flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setOpen(false)}>Annulla</Button><Button type="submit" className="bg-indaco hover:bg-indaco-dark" data-testid="save-articolo-btn">Salva</Button></div>
              </form>
            </DialogContent>
          </Dialog>
        }
      />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {list.map(a => (
          <div key={a.id} className="kpi-card group" data-testid={`articolo-${a.id}`}>
            <div className="flex items-start justify-between">
              <div className="w-11 h-11 rounded-lg bg-gradient-to-br from-azzurro/20 to-indaco/20 flex items-center justify-center">
                <Package size={20} className="text-indaco" weight="duotone" />
              </div>
              <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition">
                <button onClick={() => edit(a)} className="p-1 hover:bg-slate-100 rounded"><PencilSimple size={14} className="text-slate-500" /></button>
                <button onClick={() => del(a.id)} className="p-1 hover:bg-red-50 rounded"><Trash size={14} className="text-red-500" /></button>
              </div>
            </div>
            <div className="mt-4">
              <div className="overline">{a.categoria} · {a.tipo?.replace("_", " ")}</div>
              <div className="font-display text-lg font-bold mt-1">{a.descrizione}</div>
              <div className="text-xs text-slate-500 font-mono mt-1">{a.codice}</div>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2 text-xs">
              <div><div className="text-slate-400 text-[10px] uppercase tracking-wider">Prezzo</div><div className="font-mono font-semibold text-slate-900">€{a.prezzo.toFixed(2)}/{a.prezzo_tipo}</div></div>
              <div><div className="text-slate-400 text-[10px] uppercase tracking-wider">Peso</div><div className="font-mono font-semibold">{a.peso_medio} kg</div></div>
              <div><div className="text-slate-400 text-[10px] uppercase tracking-wider">Temp</div><div className="font-mono font-semibold">{a.temperatura}°C</div></div>
            </div>
            {a.barcode && <div className="mt-3 flex items-center gap-2 text-xs text-slate-500"><Barcode size={14} /><span className="font-mono">{a.barcode}</span></div>}
          </div>
        ))}
      </div>
    </div>
  );
}
