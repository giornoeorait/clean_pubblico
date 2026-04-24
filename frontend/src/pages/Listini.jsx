import React, { useCallback, useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Switch } from "../components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Plus, FloppyDisk, Pencil, Trash, Receipt, CheckCircle, Drop, Package } from "@phosphor-icons/react";
import { toast } from "sonner";

const EMPTY = { nome: "", tipo: "", descrizione: "", attivo: true };
const TIPO_LABEL = { noleggio: "Noleggio", lavaggio: "Lavaggio" };
const TIPO_ICON = { noleggio: Package, lavaggio: Drop };
const TIPO_COLOR = { noleggio: "text-indaco", lavaggio: "text-celeste" };

export default function Listini() {
  const [list, setList] = useState([]);
  const [selected, setSelected] = useState(null); // listino corrente
  const [prezzi, setPrezzi] = useState([]);
  const [dirty, setDirty] = useState({}); // articolo_id -> prezzo
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);

  const loadList = useCallback(async () => {
    const { data } = await api.get("/listini");
    setList(data);
    if (!selected && data.length > 0) setSelected(data[0]);
  }, [selected]);

  const loadPrezzi = useCallback(async (lid) => {
    const { data } = await api.get(`/listini/${lid}/prezzi`);
    // API may return {listino, rows} (FASE 2) or legacy [array]
    const rows = Array.isArray(data) ? data : data.rows;
    setPrezzi(rows); setDirty({});
  }, []);

  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => { if (selected?.id) loadPrezzi(selected.id); }, [selected, loadPrezzi]);

  const openNew = () => { setEditing(null); setForm(EMPTY); setFormOpen(true); };
  const openEdit = (l) => { setEditing(l); setForm({ nome: l.nome, tipo: l.tipo || "lavaggio", descrizione: l.descrizione || "", attivo: !!l.attivo }); setFormOpen(true); };

  const saveListino = async (e) => {
    e.preventDefault();
    if (!editing && !form.tipo) { toast.error("Seleziona il tipo di listino"); return; }
    try {
      if (editing) {
        // tipo is immutable after creation
        const { tipo: _t, ...patch } = form;
        await api.patch(`/listini/${editing.id}`, patch); toast.success("Listino aggiornato");
      }
      else { await api.post("/listini", form); toast.success("Listino creato"); }
      setFormOpen(false); loadList();
    } catch (e2) { toast.error(e2.response?.data?.detail || "Errore"); }
  };

  const delListino = async (l) => {
    if (!window.confirm(`Eliminare il listino "${l.nome}"?`)) return;
    try { await api.delete(`/listini/${l.id}`); toast.success("Eliminato"); setSelected(null); loadList(); }
    catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const onPriceChange = (articoloId, v) => {
    setDirty(d => ({ ...d, [articoloId]: v }));
  };

  const savePrezzi = async () => {
    const items = Object.entries(dirty).map(([articolo_id, prezzo]) => ({ articolo_id, prezzo: parseFloat(prezzo) || 0 }));
    if (items.length === 0) { toast.info("Nessuna modifica"); return; }
    try {
      const { data } = await api.put(`/listini/${selected.id}/prezzi`, { items });
      toast.success(`${data.updated} prezzi salvati`); loadPrezzi(selected.id);
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Commerciale"
        title="Listini prezzi"
        subtitle="Gestione listini e prezzi articoli. Assegna poi un listino a ogni cliente per l'automazione DDT."
        actions={
          <Dialog open={formOpen} onOpenChange={setFormOpen}>
            <DialogTrigger asChild>
              <Button onClick={openNew} className="bg-indaco hover:bg-indaco-dark" data-testid="new-listino-btn">
                <Plus size={16} className="mr-1" />Nuovo listino
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>{editing ? "Modifica listino" : "Nuovo listino"}</DialogTitle></DialogHeader>
              <form onSubmit={saveListino} className="space-y-3">
                {!editing && (
                  <div>
                    <Label>Tipo listino * <span className="text-xs text-slate-400 font-normal">(non modificabile dopo la creazione)</span></Label>
                    <div className="grid grid-cols-2 gap-2 mt-1">
                      {["noleggio","lavaggio"].map(t => {
                        const active = form.tipo === t;
                        const Icon = TIPO_ICON[t];
                        return (
                          <button key={t} type="button" onClick={() => setForm({...form, tipo: t})}
                            className={`p-3 rounded-lg border-2 transition-all text-left ${active ? "border-indaco bg-indaco/5" : "border-slate-200 hover:border-slate-300"}`}
                            data-testid={`listino-tipo-${t}`}>
                            <Icon size={20} className={active ? "text-indaco" : "text-slate-400"} weight={active ? "fill" : "regular"} />
                            <div className={`font-semibold mt-1 ${active ? "text-indaco" : "text-slate-700"}`}>{TIPO_LABEL[t]}</div>
                            <div className="text-[11px] text-slate-500">Usa <b>prezzo_{t}</b> come default</div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
                {editing && (
                  <div className="text-xs bg-slate-100 rounded px-3 py-2 font-mono">Tipo: <b className={TIPO_COLOR[editing.tipo] || ""}>{TIPO_LABEL[editing.tipo] || "—"}</b></div>
                )}
                <div><Label>Nome *</Label><Input required value={form.nome} onChange={e => setForm({...form, nome: e.target.value})} data-testid="listino-nome" /></div>
                <div><Label>Descrizione</Label><Textarea rows={2} value={form.descrizione} onChange={e => setForm({...form, descrizione: e.target.value})} /></div>
                <label className="flex items-center gap-2 cursor-pointer">
                  <Switch checked={form.attivo} onCheckedChange={v => setForm({...form, attivo: v})} data-testid="listino-attivo" />
                  <span className="text-sm">Attivo</span>
                </label>
                <div className="flex justify-end gap-2 pt-2">
                  <Button type="button" variant="outline" onClick={() => setFormOpen(false)}>Annulla</Button>
                  <Button type="submit" className="bg-indaco hover:bg-indaco-dark" data-testid="save-listino-btn"><FloppyDisk size={14} className="mr-1" />Salva</Button>
                </div>
              </form>
            </DialogContent>
          </Dialog>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <aside className="lg:col-span-1 space-y-2">
          {list.map(l => (
            <button
              key={l.id}
              onClick={() => setSelected(l)}
              className={`w-full text-left kpi-card transition ${selected?.id === l.id ? "ring-2 ring-indaco bg-indaco/5" : ""}`}
              data-testid={`listino-${l.id}`}
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-display font-bold">{l.nome}</div>
                  <div className="text-xs text-slate-500 mt-0.5">{l.descrizione || "—"}</div>
                  {l.tipo && (
                    <span className={`inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider mt-1 px-1.5 py-0.5 rounded ${l.tipo === "noleggio" ? "bg-indaco/10 text-indaco" : "bg-celeste/10 text-azzurro"}`}>
                      {TIPO_LABEL[l.tipo]}
                    </span>
                  )}
                </div>
                {l.attivo ? <CheckCircle size={16} className="text-emerald-500" weight="fill" /> : null}
              </div>
            </button>
          ))}
          {list.length === 0 && <div className="kpi-card text-center text-sm text-slate-400 py-8">Nessun listino creato</div>}
        </aside>

        <main className="lg:col-span-3">
          {selected ? (
            <>
              <div className="kpi-card mb-4 flex items-center justify-between flex-wrap gap-2">
                <div>
                  <div className="overline">Listino</div>
                  <h3 className="font-display text-xl font-bold">{selected.nome}</h3>
                  <div className="text-xs text-slate-500">{selected.descrizione || ""}</div>
                </div>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => openEdit(selected)}><Pencil size={14} className="mr-1" />Modifica</Button>
                  <Button variant="outline" size="sm" onClick={() => delListino(selected)} className="text-red-600 border-red-200"><Trash size={14} className="mr-1" />Elimina</Button>
                  <Button size="sm" onClick={savePrezzi} className="bg-indaco hover:bg-indaco-dark" data-testid="save-prezzi-btn"><FloppyDisk size={14} className="mr-1" />Salva prezzi ({Object.keys(dirty).length})</Button>
                </div>
              </div>

              <div className="kpi-card p-0 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-xs uppercase tracking-widest text-slate-500 border-b border-slate-200">
                    <tr>
                      <th className="text-left py-3 px-4">Codice</th>
                      <th className="text-left py-3 px-4">Descrizione</th>
                      <th className="text-center py-3 px-4">U.M.</th>
                      <th className="text-right py-3 px-4">Prezzo default</th>
                      <th className="text-right py-3 px-4">Prezzo listino</th>
                    </tr>
                  </thead>
                  <tbody>
                    {prezzi.map(p => {
                      const current = dirty[p.articolo_id] ?? (p.prezzo ?? "");
                      const isDirty = p.articolo_id in dirty;
                      return (
                        <tr key={p.articolo_id} className={`border-b border-slate-100 ${isDirty ? "bg-amber-50/50" : ""}`} data-testid={`prezzo-row-${p.articolo_id}`}>
                          <td className="py-2 px-4 font-mono text-xs">{p.codice}</td>
                          <td className="py-2 px-4">{p.descrizione}</td>
                          <td className="py-2 px-4 text-center text-xs">{p.unita_misura}</td>
                          <td className="py-2 px-4 text-right font-mono text-slate-500">€ {p.prezzo_default.toFixed(2)}</td>
                          <td className="py-2 px-4 text-right">
                            <Input
                              type="number" step="0.01" min="0"
                              value={current} onChange={e => onPriceChange(p.articolo_id, e.target.value)}
                              className="w-28 text-right font-mono"
                              placeholder="—"
                              data-testid={`prezzo-input-${p.articolo_id}`}
                            />
                          </td>
                        </tr>
                      );
                    })}
                    {prezzi.length === 0 && <tr><td colSpan="5" className="text-center py-8 text-slate-400">Nessun articolo. Crea prima gli articoli nell'anagrafica.</td></tr>}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div className="kpi-card text-center py-16 text-slate-400">
              <Receipt size={48} weight="duotone" className="mx-auto mb-3 text-slate-300" />
              Seleziona un listino o creane uno nuovo
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
