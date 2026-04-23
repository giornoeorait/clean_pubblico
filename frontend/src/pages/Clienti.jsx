import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Plus, MagnifyingGlass, Buildings, PencilSimple, Trash } from "@phosphor-icons/react";
import { toast } from "sonner";

const EMPTY = {
  ragione_sociale: "", partita_iva: "", codice_fiscale: "", indirizzo: "",
  email: "", telefono: "", tipologia: "hotel", listino: "standard",
  condizioni_pagamento: "30gg", giorni_ritiro: [], sla_ore: 48, note: "", attivo: true,
};

export default function Clienti() {
  const [list, setList] = useState([]);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [editing, setEditing] = useState(null);

  const fetch = async () => {
    const { data } = await api.get("/clienti" + (q ? `?q=${encodeURIComponent(q)}` : ""));
    setList(data);
  };

  useEffect(() => { fetch(); }, [q]);

  const save = async (e) => {
    e.preventDefault();
    try {
      if (editing) {
        await api.patch(`/clienti/${editing}`, form);
        toast.success("Cliente aggiornato");
      } else {
        await api.post("/clienti", form);
        toast.success("Cliente creato");
      }
      setOpen(false); setEditing(null); setForm(EMPTY);
      fetch();
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const edit = (c) => { setForm({ ...EMPTY, ...c }); setEditing(c.id); setOpen(true); };
  const del = async (id) => {
    if (!window.confirm("Eliminare cliente?")) return;
    await api.delete(`/clienti/${id}`); toast.success("Eliminato"); fetch();
  };

  return (
    <div>
      <PageHeader
        eyebrow="Anagrafica"
        title="Clienti"
        subtitle="Hotel, ospedali, ristoranti, industrie. Gestione contratti, SLA e condizioni commerciali."
        actions={
          <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setEditing(null); setForm(EMPTY); } }}>
            <DialogTrigger asChild>
              <Button className="bg-indaco hover:bg-indaco-dark" data-testid="new-cliente-btn"><Plus size={16} weight="bold" className="mr-1" /> Nuovo Cliente</Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl">
              <DialogHeader><DialogTitle>{editing ? "Modifica cliente" : "Nuovo cliente"}</DialogTitle></DialogHeader>
              <form onSubmit={save} className="grid grid-cols-2 gap-4" data-testid="cliente-form">
                <div className="col-span-2"><Label>Ragione sociale *</Label><Input required value={form.ragione_sociale} onChange={e => setForm({...form, ragione_sociale: e.target.value})} data-testid="cliente-ragione-sociale" /></div>
                <div><Label>Partita IVA</Label><Input value={form.partita_iva} onChange={e => setForm({...form, partita_iva: e.target.value})} /></div>
                <div><Label>Codice Fiscale</Label><Input value={form.codice_fiscale} onChange={e => setForm({...form, codice_fiscale: e.target.value})} /></div>
                <div className="col-span-2"><Label>Indirizzo</Label><Input value={form.indirizzo} onChange={e => setForm({...form, indirizzo: e.target.value})} /></div>
                <div><Label>Email</Label><Input type="email" value={form.email} onChange={e => setForm({...form, email: e.target.value})} /></div>
                <div><Label>Telefono</Label><Input value={form.telefono} onChange={e => setForm({...form, telefono: e.target.value})} /></div>
                <div>
                  <Label>Tipologia</Label>
                  <Select value={form.tipologia} onValueChange={v => setForm({...form, tipologia: v})}>
                    <SelectTrigger data-testid="cliente-tipologia"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="hotel">Hotel</SelectItem>
                      <SelectItem value="ristorante">Ristorante</SelectItem>
                      <SelectItem value="ospedale">Ospedale</SelectItem>
                      <SelectItem value="industria">Industria</SelectItem>
                      <SelectItem value="altro">Altro</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div><Label>Condizioni pagamento</Label><Input value={form.condizioni_pagamento} onChange={e => setForm({...form, condizioni_pagamento: e.target.value})} /></div>
                <div><Label>SLA (ore)</Label><Input type="number" value={form.sla_ore} onChange={e => setForm({...form, sla_ore: parseInt(e.target.value)})} /></div>
                <div><Label>Listino</Label><Input value={form.listino} onChange={e => setForm({...form, listino: e.target.value})} /></div>
                <div className="col-span-2"><Label>Note</Label><Input value={form.note} onChange={e => setForm({...form, note: e.target.value})} /></div>
                <div className="col-span-2 flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setOpen(false)}>Annulla</Button><Button type="submit" className="bg-indaco hover:bg-indaco-dark" data-testid="save-cliente-btn">Salva</Button></div>
              </form>
            </DialogContent>
          </Dialog>
        }
      />

      <div className="kpi-card mb-6">
        <div className="relative">
          <MagnifyingGlass size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={q} onChange={e => setQ(e.target.value)}
            placeholder="Cerca per ragione sociale..."
            className="w-full pl-10 pr-4 py-2 border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indaco"
            data-testid="clienti-search"
          />
        </div>
      </div>

      <div className="kpi-card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Ragione sociale</th><th>Tipologia</th><th>P.IVA</th><th>Contatto</th><th>SLA</th><th>Azioni</th>
              </tr>
            </thead>
            <tbody>
              {list.map(c => (
                <tr key={c.id} data-testid={`cliente-row-${c.id}`}>
                  <td>
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-celeste/20 to-indaco/20 flex items-center justify-center">
                        <Buildings size={16} className="text-indaco" weight="duotone" />
                      </div>
                      <div>
                        <div className="font-medium text-slate-900">{c.ragione_sociale}</div>
                        <div className="text-xs text-slate-500 font-mono">{c.indirizzo}</div>
                      </div>
                    </div>
                  </td>
                  <td><span className="text-xs uppercase tracking-wider text-slate-500">{c.tipologia}</span></td>
                  <td className="font-mono text-xs">{c.partita_iva || "—"}</td>
                  <td><div className="text-xs">{c.email}</div><div className="text-xs text-slate-500 font-mono">{c.telefono}</div></td>
                  <td><span className="font-mono text-xs">{c.sla_ore}h</span></td>
                  <td>
                    <div className="flex gap-1">
                      <button onClick={() => edit(c)} className="p-1.5 hover:bg-slate-100 rounded" data-testid={`edit-${c.id}`}><PencilSimple size={16} className="text-slate-500" /></button>
                      <button onClick={() => del(c.id)} className="p-1.5 hover:bg-red-50 rounded" data-testid={`del-${c.id}`}><Trash size={16} className="text-red-500" /></button>
                    </div>
                  </td>
                </tr>
              ))}
              {list.length === 0 && <tr><td colSpan={6} className="text-center py-12 text-slate-400">Nessun cliente trovato</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
