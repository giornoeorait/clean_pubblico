import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import StatoBadge from "../components/StatoBadge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Plus, ShieldWarning, Warning, CheckCircle } from "@phosphor-icons/react";
import { toast } from "sonner";
import FileUpload from "../components/FileUpload";

const EMPTY = { lotto_id: "", tipo_difetto: "", gravita: "media", foto_urls: [], responsabile: "", azione_correttiva: "" };

export default function Qualita() {
  const [list, setList] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [fotos, setFotos] = useState([]);
  const [open, setOpen] = useState(false);

  const fetch = async () => { const { data } = await api.get("/non-conformita"); setList(data); };
  useEffect(() => { fetch(); }, []);

  const save = async (e) => {
    e.preventDefault();
    try {
      await api.post("/non-conformita", { ...form, foto_urls: fotos.map(f => f.url) });
      toast.success("Non conformità registrata");
      setOpen(false); setForm(EMPTY); setFotos([]); fetch();
    } catch (e) { toast.error(e.response?.data?.detail); }
  };

  const risolvi = async (id) => { await api.patch(`/non-conformita/${id}`, { stato: "risolta" }); toast.success("NC risolta"); fetch(); };

  const grouped = { aperta: [], in_lavorazione: [], risolta: [] };
  list.forEach(n => grouped[n.stato]?.push(n));

  return (
    <div>
      <PageHeader
        eyebrow="Qualità"
        title="Non Conformità"
        subtitle="Registrazione difetti, gravità, responsabili, azioni correttive. Storico completo per audit."
        actions={
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild><Button className="bg-indaco hover:bg-indaco-dark" data-testid="new-nc-btn"><Plus size={16} className="mr-1" />Nuova NC</Button></DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Segnala non conformità</DialogTitle></DialogHeader>
              <form onSubmit={save} className="space-y-4">
                <div><Label>Tipo difetto *</Label><Input required value={form.tipo_difetto} onChange={e => setForm({...form, tipo_difetto: e.target.value})} placeholder="es. Macchia residua" /></div>
                <div>
                  <Label>Gravità</Label>
                  <Select value={form.gravita} onValueChange={v => setForm({...form, gravita: v})}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="bassa">Bassa</SelectItem>
                      <SelectItem value="media">Media</SelectItem>
                      <SelectItem value="alta">Alta</SelectItem>
                      <SelectItem value="critica">Critica</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div><Label>Responsabile</Label><Input value={form.responsabile} onChange={e => setForm({...form, responsabile: e.target.value})} /></div>
                <div><Label>Azione correttiva</Label><Textarea rows={3} value={form.azione_correttiva} onChange={e => setForm({...form, azione_correttiva: e.target.value})} /></div>
                <div><Label>Foto del difetto</Label><FileUpload value={fotos} onChange={setFotos} context="non-conformita" label="Aggiungi foto" testId="nc-foto" /></div>
                <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setOpen(false)}>Annulla</Button><Button type="submit" className="bg-indaco hover:bg-indaco-dark">Registra</Button></div>
              </form>
            </DialogContent>
          </Dialog>
        }
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="kpi-card">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-red-100 flex items-center justify-center"><Warning size={20} weight="duotone" className="text-red-600" /></div>
            <div><div className="overline">Aperte</div><div className="font-display text-2xl font-bold">{grouped.aperta.length}</div></div>
          </div>
        </div>
        <div className="kpi-card">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center"><ShieldWarning size={20} weight="duotone" className="text-amber-600" /></div>
            <div><div className="overline">In lavorazione</div><div className="font-display text-2xl font-bold">{grouped.in_lavorazione.length}</div></div>
          </div>
        </div>
        <div className="kpi-card">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-emerald-100 flex items-center justify-center"><CheckCircle size={20} weight="duotone" className="text-emerald-600" /></div>
            <div><div className="overline">Risolte</div><div className="font-display text-2xl font-bold">{grouped.risolta.length}</div></div>
          </div>
        </div>
      </div>

      <div className="kpi-card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead><tr><th>Tipo difetto</th><th>Gravità</th><th>Responsabile</th><th>Segnalato da</th><th>Data</th><th>Stato</th><th>Azioni</th></tr></thead>
            <tbody>
              {list.map(n => (
                <tr key={n.id} data-testid={`nc-${n.id}`}>
                  <td className="font-medium">{n.tipo_difetto}</td>
                  <td><StatoBadge stato={n.gravita} /></td>
                  <td className="text-sm">{n.responsabile || "—"}</td>
                  <td className="text-xs text-slate-500">{n.segnalato_da}</td>
                  <td className="text-xs text-slate-500 font-mono">{new Date(n.created_at).toLocaleDateString("it-IT")}</td>
                  <td><StatoBadge stato={n.stato} /></td>
                  <td>{n.stato !== "risolta" && <Button size="sm" variant="outline" onClick={() => risolvi(n.id)} data-testid={`resolve-${n.id}`}>Risolvi</Button>}</td>
                </tr>
              ))}
              {list.length === 0 && <tr><td colSpan={7} className="text-center py-12 text-slate-400">Nessuna non conformità registrata</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
