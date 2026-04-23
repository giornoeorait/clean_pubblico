import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import StatoBadge from "../components/StatoBadge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Plus, HardDrives, Wrench, Lightning } from "@phosphor-icons/react";
import { toast } from "sonner";

const EMPTY = { codice: "", tipo: "lavatrice", capacita_kg: 60, stato: "disponibile", reparto: "lavaggio", ore_lavoro: 0 };

export default function Macchine() {
  const [list, setList] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);

  const fetch = async () => { const { data } = await api.get("/macchine"); setList(data); };
  useEffect(() => { fetch(); }, []);

  const save = async (e) => { e.preventDefault(); try { await api.post("/macchine", form); toast.success("Macchina aggiunta"); setOpen(false); setForm(EMPTY); fetch(); } catch (e) { toast.error(e.response?.data?.detail); } };

  const changeStato = async (id, stato) => { await api.patch(`/macchine/${id}`, { stato }); toast.success("Stato aggiornato"); fetch(); };

  const byReparto = list.reduce((acc, m) => { (acc[m.reparto] = acc[m.reparto] || []).push(m); return acc; }, {});

  return (
    <div>
      <PageHeader
        eyebrow="Anagrafica"
        title="Macchine & Impianti"
        subtitle="Lavatrici, asciugatrici, stiratrici. Stato real-time, ore lavoro e manutenzioni."
        actions={
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild><Button className="bg-indaco hover:bg-indaco-dark" data-testid="new-macchina-btn"><Plus size={16} weight="bold" className="mr-1" />Nuova Macchina</Button></DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Nuova macchina</DialogTitle></DialogHeader>
              <form onSubmit={save} className="space-y-4">
                <div><Label>Codice *</Label><Input required value={form.codice} onChange={e => setForm({...form, codice: e.target.value})} /></div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label>Tipo</Label>
                    <Select value={form.tipo} onValueChange={v => setForm({...form, tipo: v, reparto: v === "lavatrice" ? "lavaggio" : v === "asciugatrice" ? "asciugatura" : "stiratura"})}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="lavatrice">Lavatrice</SelectItem>
                        <SelectItem value="asciugatrice">Asciugatrice</SelectItem>
                        <SelectItem value="stiratrice">Stiratrice</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div><Label>Capacità (kg)</Label><Input type="number" value={form.capacita_kg} onChange={e => setForm({...form, capacita_kg: parseFloat(e.target.value)})} /></div>
                </div>
                <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setOpen(false)}>Annulla</Button><Button type="submit" className="bg-indaco hover:bg-indaco-dark">Salva</Button></div>
              </form>
            </DialogContent>
          </Dialog>
        }
      />

      {Object.entries(byReparto).map(([reparto, items]) => (
        <div key={reparto} className="mb-8">
          <div className="overline mb-4">Reparto {reparto}</div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {items.map(m => (
              <div key={m.id} className="kpi-card" data-testid={`macchina-${m.codice}`}>
                <div className="flex items-start justify-between mb-4">
                  <div className="w-12 h-12 rounded-lg bg-slate-900 flex items-center justify-center">
                    <HardDrives size={22} weight="duotone" className="text-celeste" />
                  </div>
                  <StatoBadge stato={m.stato} />
                </div>
                <div className="font-display text-xl font-bold">{m.codice}</div>
                <div className="text-xs text-slate-500 capitalize">{m.tipo}</div>
                <div className="mt-4 pt-4 border-t border-slate-100 grid grid-cols-2 gap-2 text-xs">
                  <div><div className="text-slate-400 uppercase text-[10px] tracking-wider">Capacità</div><div className="font-mono font-semibold">{m.capacita_kg} kg</div></div>
                  <div><div className="text-slate-400 uppercase text-[10px] tracking-wider">Ore</div><div className="font-mono font-semibold">{m.ore_lavoro.toLocaleString()}h</div></div>
                </div>
                <div className="mt-3 flex gap-1 text-xs">
                  <button onClick={() => changeStato(m.id, "disponibile")} className="flex-1 py-1.5 bg-emerald-50 text-emerald-700 rounded hover:bg-emerald-100" data-testid={`disponibile-${m.codice}`}><Lightning size={12} className="inline mr-1" />Disp.</button>
                  <button onClick={() => changeStato(m.id, "manutenzione")} className="flex-1 py-1.5 bg-amber-50 text-amber-700 rounded hover:bg-amber-100"><Wrench size={12} className="inline mr-1" />Manut.</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
