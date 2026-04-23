import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import StatoBadge from "../components/StatoBadge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Plus, Receipt, Euro, Trash } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function Fatture() {
  const [list, setList] = useState([]);
  const [clienti, setClienti] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ cliente_id: "", data: new Date().toISOString().split("T")[0], righe: [{ descrizione: "", quantita: 1, prezzo: 0 }], iva_pct: 22 });

  const fetch = async () => {
    const [f, c] = await Promise.all([api.get("/fatture"), api.get("/clienti")]);
    setList(f.data); setClienti(c.data);
  };
  useEffect(() => { fetch(); }, []);

  const addRiga = () => setForm({...form, righe: [...form.righe, { descrizione: "", quantita: 1, prezzo: 0 }]});
  const delRiga = (i) => setForm({...form, righe: form.righe.filter((_, idx) => idx !== i)});
  const updRiga = (i, k, v) => setForm({...form, righe: form.righe.map((r, idx) => idx === i ? {...r, [k]: v, totale: idx === i && (k === "quantita" || k === "prezzo") ? Number(k === "quantita" ? v : r.quantita) * Number(k === "prezzo" ? v : r.prezzo) : r.totale} : r)});

  const total = form.righe.reduce((s, r) => s + (Number(r.quantita) * Number(r.prezzo)), 0);

  const save = async (e) => {
    e.preventDefault();
    try {
      const righe = form.righe.map(r => ({ ...r, totale: Number(r.quantita) * Number(r.prezzo) }));
      await api.post("/fatture", { ...form, righe });
      toast.success("Fattura creata"); setOpen(false); setForm({ ...form, cliente_id: "", righe: [{ descrizione: "", quantita: 1, prezzo: 0 }] });
      fetch();
    } catch (e) { toast.error(e.response?.data?.detail); }
  };

  const changeStato = async (id, stato) => { await api.patch(`/fatture/${id}`, { stato }); toast.success("Aggiornata"); fetch(); };

  const cm = {}; clienti.forEach(c => cm[c.id] = c.ragione_sociale);

  return (
    <div>
      <PageHeader
        eyebrow="ERP"
        title="Fatturazione"
        subtitle="Pre-fatture, fatture, scadenziario. Tariffazione a capo, a kg, a canone."
        actions={
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild><Button className="bg-indaco hover:bg-indaco-dark" data-testid="new-fattura-btn"><Plus size={16} className="mr-1" />Nuova Fattura</Button></DialogTrigger>
            <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
              <DialogHeader><DialogTitle>Nuova fattura</DialogTitle></DialogHeader>
              <form onSubmit={save} className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label>Cliente *</Label>
                    <Select value={form.cliente_id} onValueChange={v => setForm({...form, cliente_id: v})}>
                      <SelectTrigger><SelectValue placeholder="Seleziona cliente" /></SelectTrigger>
                      <SelectContent>{clienti.map(c => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <div><Label>Data</Label><Input type="date" value={form.data} onChange={e => setForm({...form, data: e.target.value})} /></div>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-2">
                    <Label>Righe</Label>
                    <Button type="button" size="sm" variant="outline" onClick={addRiga}><Plus size={14} className="mr-1" />Riga</Button>
                  </div>
                  <div className="space-y-2">
                    {form.righe.map((r, i) => (
                      <div key={i} className="grid grid-cols-12 gap-2">
                        <Input className="col-span-6" placeholder="Descrizione" value={r.descrizione} onChange={e => updRiga(i, "descrizione", e.target.value)} />
                        <Input className="col-span-2" type="number" placeholder="Qta" value={r.quantita} onChange={e => updRiga(i, "quantita", e.target.value)} />
                        <Input className="col-span-3" type="number" step="0.01" placeholder="€" value={r.prezzo} onChange={e => updRiga(i, "prezzo", e.target.value)} />
                        <Button type="button" variant="outline" className="col-span-1 text-red-500" onClick={() => delRiga(i)}><Trash size={14} /></Button>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="flex items-center justify-between bg-slate-50 p-4 rounded-md">
                  <div className="text-sm">IVA <input type="number" className="w-16 px-2 py-1 border border-slate-200 rounded mx-1 font-mono" value={form.iva_pct} onChange={e => setForm({...form, iva_pct: Number(e.target.value)})} />%</div>
                  <div className="font-display text-2xl font-bold">€ {(total * (1 + form.iva_pct/100)).toFixed(2)}</div>
                </div>

                <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setOpen(false)}>Annulla</Button><Button type="submit" className="bg-indaco hover:bg-indaco-dark">Crea</Button></div>
              </form>
            </DialogContent>
          </Dialog>
        }
      />

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        {["bozza", "emessa", "pagata", "scaduta"].map(s => {
          const items = list.filter(f => f.stato === s);
          const tot = items.reduce((acc, x) => acc + (x.totale || 0), 0);
          return (
            <div key={s} className="kpi-card">
              <div className="overline capitalize">{s}</div>
              <div className="font-display text-2xl font-bold mt-2">{items.length}</div>
              <div className="text-xs text-slate-500 font-mono">€ {tot.toFixed(2)}</div>
            </div>
          );
        })}
      </div>

      <div className="kpi-card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead><tr><th>Numero</th><th>Cliente</th><th>Data</th><th>Imponibile</th><th>IVA</th><th>Totale</th><th>Stato</th><th>Azioni</th></tr></thead>
            <tbody>
              {list.map(f => (
                <tr key={f.id} data-testid={`fattura-${f.numero}`}>
                  <td className="font-mono font-bold text-indaco">{f.numero}</td>
                  <td>{cm[f.cliente_id]}</td>
                  <td className="text-xs font-mono">{f.data}</td>
                  <td className="font-mono">€ {f.imponibile?.toFixed(2)}</td>
                  <td className="font-mono text-xs">€ {f.iva?.toFixed(2)}</td>
                  <td className="font-mono font-bold">€ {f.totale?.toFixed(2)}</td>
                  <td><StatoBadge stato={f.stato} /></td>
                  <td>
                    {f.stato === "bozza" && <Button size="sm" variant="outline" onClick={() => changeStato(f.id, "emessa")}>Emetti</Button>}
                    {f.stato === "emessa" && <Button size="sm" variant="outline" onClick={() => changeStato(f.id, "pagata")}>Pagata</Button>}
                  </td>
                </tr>
              ))}
              {list.length === 0 && <tr><td colSpan={8} className="text-center py-12 text-slate-400">Nessuna fattura</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
