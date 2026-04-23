import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import StatoBadge from "../components/StatoBadge";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { CheckCircle, Circle, Path, ArrowRight, Clock } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Textarea } from "../components/ui/textarea";
import { Label } from "../components/ui/label";
import { toast } from "sonner";

const STATI = ["ritirato", "ricevuto", "smistato", "lavato", "asciugato", "stirato", "confezionato", "pronto", "consegnato"];

export default function Lotti() {
  const [list, setList] = useState([]);
  const [selected, setSelected] = useState(null);
  const [filter, setFilter] = useState("");
  const [newStato, setNewStato] = useState("");
  const [nota, setNota] = useState("");
  const [clienti, setClienti] = useState({});

  const fetch = async () => {
    const [l, c] = await Promise.all([api.get("/lotti" + (filter ? `?stato=${filter}` : "")), api.get("/clienti")]);
    setList(l.data);
    const map = {}; c.data.forEach(x => { map[x.id] = x.ragione_sociale; }); setClienti(map);
  };
  useEffect(() => { fetch(); }, [filter]);

  const cambiaStato = async () => {
    if (!newStato) return;
    await api.post(`/lotti/${selected.id}/cambia-stato`, { nuovo_stato: newStato, note: nota });
    toast.success(`Stato aggiornato a ${newStato}`);
    const { data } = await api.get(`/lotti/${selected.id}`);
    setSelected(data); setNewStato(""); setNota("");
    fetch();
  };

  return (
    <div>
      <PageHeader
        eyebrow="Workflow"
        title="Tracciabilità Lotti"
        subtitle="9 stati operativi — da 'ritirato' a 'consegnato'. Ogni transizione registra timestamp, operatore, macchina ed esito."
      />

      <div className="flex flex-wrap gap-2 mb-6">
        <button onClick={() => setFilter("")} className={`px-3 py-1.5 text-xs font-semibold rounded-md ${!filter ? "bg-indaco text-white" : "bg-white border border-slate-200 text-slate-600"}`} data-testid="filter-all">Tutti</button>
        {STATI.map(s => (
          <button key={s} onClick={() => setFilter(s)} className={`px-3 py-1.5 text-xs font-semibold rounded-md capitalize ${filter === s ? "bg-indaco text-white" : "bg-white border border-slate-200 text-slate-600 hover:border-indaco"}`} data-testid={`filter-${s}`}>{s}</button>
        ))}
      </div>

      <div className="kpi-card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr><th>Lotto</th><th>Cliente</th><th>Quantità</th><th>Peso</th><th>Priorità</th><th>Stato</th><th>Timeline</th></tr>
            </thead>
            <tbody>
              {list.map(l => (
                <tr key={l.id} className="cursor-pointer" onClick={() => setSelected(l)} data-testid={`lotto-${l.numero}`}>
                  <td className="font-mono text-xs font-semibold text-indaco">{l.numero}</td>
                  <td className="text-sm">{clienti[l.cliente_id] || "—"}</td>
                  <td className="font-mono">{l.quantita}</td>
                  <td className="font-mono">{l.peso} kg</td>
                  <td><StatoBadge stato={l.priorita} /></td>
                  <td><StatoBadge stato={l.stato_corrente} /></td>
                  <td>
                    <div className="flex items-center gap-0.5">
                      {STATI.map((s, i) => {
                        const done = STATI.indexOf(l.stato_corrente) >= i;
                        return <div key={s} className={`w-4 h-1.5 rounded-full ${done ? "bg-azzurro" : "bg-slate-200"}`} title={s}></div>;
                      })}
                    </div>
                  </td>
                </tr>
              ))}
              {list.length === 0 && <tr><td colSpan={7} className="text-center py-12 text-slate-400">Nessun lotto</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      <Dialog open={!!selected} onOpenChange={(o) => !o && setSelected(null)}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          {selected && (
            <>
              <DialogHeader>
                <DialogTitle className="font-display flex items-center gap-2">
                  <Path size={24} className="text-indaco" weight="duotone" />
                  Lotto {selected.numero}
                </DialogTitle>
              </DialogHeader>
              <div className="grid grid-cols-3 gap-4 mb-6 mt-2">
                <div><div className="overline">Cliente</div><div className="text-sm font-medium mt-1">{clienti[selected.cliente_id]}</div></div>
                <div><div className="overline">Quantità</div><div className="font-mono font-bold mt-1">{selected.quantita} pz</div></div>
                <div><div className="overline">Peso</div><div className="font-mono font-bold mt-1">{selected.peso} kg</div></div>
              </div>

              <div className="mb-6">
                <div className="overline mb-3">Timeline tracciabilità</div>
                <div className="relative pl-8 space-y-0">
                  {STATI.map((s, i) => {
                    const entry = (selected.storico_stati || []).find(e => e.stato === s);
                    const idx = STATI.indexOf(selected.stato_corrente);
                    const done = i <= idx;
                    const current = i === idx;
                    return (
                      <div key={s} className="relative pb-6">
                        {i < STATI.length - 1 && <div className={`absolute left-[-20px] top-6 bottom-0 w-0.5 ${done ? "bg-azzurro" : "bg-slate-200"}`}></div>}
                        <div className={`absolute left-[-28px] top-0 w-5 h-5 rounded-full flex items-center justify-center ${current ? "bg-azzurro ring-4 ring-azzurro/20 animate-pulse-dot" : done ? "bg-emerald-500" : "bg-slate-200"}`}>
                          {done && !current && <CheckCircle size={12} weight="fill" className="text-white" />}
                          {current && <Circle size={8} weight="fill" className="text-white" />}
                        </div>
                        <div>
                          <div className={`text-sm font-semibold capitalize ${done ? "text-slate-900" : "text-slate-400"}`}>{s}</div>
                          {entry && (
                            <div className="text-xs text-slate-500 font-mono mt-0.5 flex items-center gap-2">
                              <Clock size={12} />
                              <span>{new Date(entry.timestamp).toLocaleString("it-IT")}</span>
                              <span>· {entry.operatore}</span>
                              {entry.note && <span>· {entry.note}</span>}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="border-t border-slate-200 pt-4">
                <div className="overline mb-3">Cambia stato</div>
                <div className="grid grid-cols-2 gap-2">
                  <Select value={newStato} onValueChange={setNewStato}>
                    <SelectTrigger data-testid="change-stato-select"><SelectValue placeholder="Nuovo stato" /></SelectTrigger>
                    <SelectContent>{STATI.map(s => <SelectItem key={s} value={s} className="capitalize">{s}</SelectItem>)}</SelectContent>
                  </Select>
                  <Button onClick={cambiaStato} className="bg-indaco hover:bg-indaco-dark" data-testid="change-stato-btn">
                    <ArrowRight size={16} className="mr-1" /> Applica
                  </Button>
                </div>
                <Textarea placeholder="Note (opzionale)" value={nota} onChange={e => setNota(e.target.value)} className="mt-2" rows={2} />
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
