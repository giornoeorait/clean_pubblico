import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import StatoBadge from "../components/StatoBadge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Plus, Truck, MapPin, Package, Calendar } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function Logistica() {
  const [list, setList] = useState([]);
  const [clienti, setClienti] = useState([]);
  const [lottiPronti, setLottiPronti] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ cliente_id: "", lotti_ids: [], data_prevista: new Date().toISOString().split("T")[0], autista: "", note: "" });

  const fetch = async () => {
    const [c, l, lp] = await Promise.all([
      api.get("/consegne"),
      api.get("/clienti"),
      api.get("/lotti?stato=pronto"),
    ]);
    setList(c.data); setClienti(l.data); setLottiPronti(lp.data);
  };
  useEffect(() => { fetch(); }, []);

  const save = async (e) => {
    e.preventDefault();
    try { await api.post("/consegne", form); toast.success("Consegna pianificata"); setOpen(false); setForm({ ...form, cliente_id: "", lotti_ids: [], autista: "", note: "" }); fetch(); }
    catch (e) { toast.error(e.response?.data?.detail); }
  };

  const changeStato = async (id, stato) => {
    await api.patch(`/consegne/${id}`, { stato });
    if (stato === "consegnata") {
      // Marca lotti come consegnati
      const c = list.find(x => x.id === id);
      if (c && c.lotti_ids) {
        for (const lid of c.lotti_ids) await api.post(`/lotti/${lid}/cambia-stato`, { nuovo_stato: "consegnato" });
      }
    }
    toast.success("Stato aggiornato"); fetch();
  };

  const cm = {}; clienti.forEach(c => cm[c.id] = c.ragione_sociale);

  return (
    <div>
      <PageHeader
        eyebrow="TMS"
        title="Logistica & Consegne"
        subtitle="Pianificazione ritiri/consegne, assegnazione autisti, tracking real-time."
        actions={
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild><Button className="bg-indaco hover:bg-indaco-dark" data-testid="new-consegna-btn"><Plus size={16} className="mr-1" />Nuova Consegna</Button></DialogTrigger>
            <DialogContent className="max-w-xl">
              <DialogHeader><DialogTitle>Pianifica Consegna</DialogTitle></DialogHeader>
              <form onSubmit={save} className="space-y-4">
                <div>
                  <Label>Cliente *</Label>
                  <Select value={form.cliente_id} onValueChange={v => setForm({...form, cliente_id: v})}>
                    <SelectTrigger data-testid="consegna-cliente"><SelectValue placeholder="Seleziona cliente" /></SelectTrigger>
                    <SelectContent>{clienti.map(c => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div><Label>Data prevista</Label><Input type="date" value={form.data_prevista} onChange={e => setForm({...form, data_prevista: e.target.value})} /></div>
                  <div><Label>Autista</Label><Input value={form.autista} onChange={e => setForm({...form, autista: e.target.value})} /></div>
                </div>
                <div>
                  <Label>Lotti da consegnare (pronti)</Label>
                  <div className="max-h-48 overflow-y-auto border border-slate-200 rounded-md p-2 space-y-1">
                    {lottiPronti.filter(l => !form.cliente_id || l.cliente_id === form.cliente_id).map(l => (
                      <label key={l.id} className="flex items-center gap-2 text-sm p-1 hover:bg-slate-50 rounded cursor-pointer">
                        <input
                          type="checkbox"
                          checked={form.lotti_ids.includes(l.id)}
                          onChange={e => {
                            if (e.target.checked) setForm({...form, lotti_ids: [...form.lotti_ids, l.id]});
                            else setForm({...form, lotti_ids: form.lotti_ids.filter(x => x !== l.id)});
                          }}
                        />
                        <span className="font-mono text-xs">{l.numero}</span>
                        <span className="text-slate-500 text-xs flex-1 truncate">{cm[l.cliente_id]}</span>
                        <span className="font-mono text-xs text-slate-400">{l.quantita} pz</span>
                      </label>
                    ))}
                    {lottiPronti.length === 0 && <div className="text-xs text-slate-400 text-center py-4">Nessun lotto pronto</div>}
                  </div>
                </div>
                <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setOpen(false)}>Annulla</Button><Button type="submit" className="bg-indaco hover:bg-indaco-dark">Pianifica</Button></div>
              </form>
            </DialogContent>
          </Dialog>
        }
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="kpi-card"><div className="flex items-center gap-3"><div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center"><Calendar size={20} weight="duotone" className="text-slate-600" /></div><div><div className="overline">Pianificate</div><div className="font-display text-2xl font-bold">{list.filter(c => c.stato === "pianificata").length}</div></div></div></div>
        <div className="kpi-card"><div className="flex items-center gap-3"><div className="w-10 h-10 rounded-lg bg-azzurro/10 flex items-center justify-center"><Truck size={20} weight="duotone" className="text-azzurro" /></div><div><div className="overline">In consegna</div><div className="font-display text-2xl font-bold">{list.filter(c => c.stato === "in_consegna").length}</div></div></div></div>
        <div className="kpi-card"><div className="flex items-center gap-3"><div className="w-10 h-10 rounded-lg bg-emerald-100 flex items-center justify-center"><Package size={20} weight="duotone" className="text-emerald-600" /></div><div><div className="overline">Consegnate</div><div className="font-display text-2xl font-bold">{list.filter(c => c.stato === "consegnata").length}</div></div></div></div>
      </div>

      <div className="space-y-3">
        {list.map(c => (
          <div key={c.id} className="kpi-card flex flex-col md:flex-row md:items-center gap-4" data-testid={`consegna-${c.numero}`}>
            <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-azzurro/20 to-indaco/20 flex items-center justify-center flex-shrink-0">
              <Truck size={22} className="text-indaco" weight="duotone" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3">
                <div className="font-mono font-bold text-indaco text-sm">{c.numero}</div>
                <StatoBadge stato={c.stato} />
              </div>
              <div className="font-display font-bold mt-1 truncate">{cm[c.cliente_id]}</div>
              <div className="text-xs text-slate-500 font-mono flex flex-wrap items-center gap-3 mt-1">
                <span><Calendar size={12} className="inline mr-1" />{(c.data_prevista || "").slice(0,10)}</span>
                {c.autista && <span>Autista: {c.autista}</span>}
                <span>{c.lotti_ids?.length || 0} lotti</span>
              </div>
            </div>
            <div className="flex gap-2 flex-wrap">
              {c.stato === "pianificata" && <Button size="sm" variant="outline" onClick={() => changeStato(c.id, "in_consegna")} data-testid={`start-${c.numero}`}>Avvia</Button>}
              {c.stato === "in_consegna" && <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700" onClick={() => changeStato(c.id, "consegnata")} data-testid={`complete-${c.numero}`}>Consegnata</Button>}
            </div>
          </div>
        ))}
        {list.length === 0 && <div className="kpi-card text-center py-12 text-slate-400">Nessuna consegna</div>}
      </div>
    </div>
  );
}
