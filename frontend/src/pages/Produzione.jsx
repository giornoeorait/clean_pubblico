import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import StatoBadge from "../components/StatoBadge";
import { Kanban, Lightning, Clock, ArrowRight } from "@phosphor-icons/react";
import { toast } from "sonner";

const COLUMNS = [
  { key: "ricevuto", label: "Ricevuto", color: "border-l-sky-400" },
  { key: "smistato", label: "Smistato", color: "border-l-sky-500" },
  { key: "lavato", label: "In Lavaggio", color: "border-l-blue-500" },
  { key: "asciugato", label: "Asciugatura", color: "border-l-cyan-500" },
  { key: "stirato", label: "Stiratura", color: "border-l-indigo-500" },
  { key: "confezionato", label: "Confezionamento", color: "border-l-violet-500" },
  { key: "pronto", label: "Pronto", color: "border-l-emerald-500" },
];

const NEXT_STATE = {
  ricevuto: "smistato", smistato: "lavato", lavato: "asciugato",
  asciugato: "stirato", stirato: "confezionato", confezionato: "pronto", pronto: "consegnato",
};

export default function Produzione() {
  const [lotti, setLotti] = useState([]);
  const [clienti, setClienti] = useState({});
  const [articoli, setArticoli] = useState({});
  const [draggingId, setDraggingId] = useState(null);

  const fetch = async () => {
    const [l, c, a] = await Promise.all([api.get("/lotti?limit=500"), api.get("/clienti"), api.get("/articoli")]);
    setLotti(l.data);
    const cm = {}; c.data.forEach(x => cm[x.id] = x.ragione_sociale); setClienti(cm);
    const am = {}; a.data.forEach(x => am[x.id] = x); setArticoli(am);
  };
  useEffect(() => { fetch(); }, []);

  const moveTo = async (lottoId, stato) => {
    await api.post(`/lotti/${lottoId}/cambia-stato`, { nuovo_stato: stato });
    toast.success(`Spostato in "${stato}"`);
    fetch();
  };

  const onDragStart = (e, id) => { setDraggingId(id); e.dataTransfer.effectAllowed = "move"; };
  const onDragOver = (e) => e.preventDefault();
  const onDrop = (e, stato) => {
    e.preventDefault();
    if (draggingId) moveTo(draggingId, stato);
    setDraggingId(null);
  };

  return (
    <div>
      <PageHeader
        eyebrow="MES"
        title="Produzione — Kanban"
        subtitle="Coda lavorazioni per reparto. Trascina un lotto tra le colonne per aggiornare lo stato in real-time."
      />

      <div className="flex gap-4 overflow-x-auto pb-4" data-testid="kanban-board">
        {COLUMNS.map(col => {
          const items = lotti.filter(l => l.stato_corrente === col.key);
          return (
            <div
              key={col.key}
              onDragOver={onDragOver}
              onDrop={(e) => onDrop(e, col.key)}
              className="flex-shrink-0 w-72 bg-slate-100 rounded-lg p-3"
              data-testid={`col-${col.key}`}
            >
              <div className="flex items-center justify-between mb-3 px-1">
                <div>
                  <div className="font-display font-bold text-slate-900 flex items-center gap-2">
                    <Kanban size={16} weight="duotone" className="text-indaco" />
                    {col.label}
                  </div>
                  <div className="text-xs text-slate-500 font-mono mt-0.5">{items.length} lotti</div>
                </div>
                <span className="bg-white border border-slate-200 text-indaco text-xs font-mono font-bold rounded-full px-2 py-0.5">{items.length}</span>
              </div>

              <div className="space-y-2 max-h-[70vh] overflow-y-auto">
                {items.map(l => (
                  <div
                    key={l.id}
                    draggable
                    onDragStart={(e) => onDragStart(e, l.id)}
                    className={`bg-white border-l-4 ${col.color} border-y border-r border-slate-200 rounded p-3 shadow-sm hover:shadow-md cursor-grab active:cursor-grabbing transition-all ${l.priorita === "urgente" ? "ring-2 ring-red-400" : ""}`}
                    data-testid={`kanban-card-${l.numero}`}
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="font-mono text-xs font-bold text-indaco">{l.numero}</div>
                      {l.priorita !== "normale" && (
                        <span className={`text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${l.priorita === "urgente" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700"}`}>
                          {l.priorita === "urgente" && <Lightning size={10} className="inline" />} {l.priorita}
                        </span>
                      )}
                    </div>
                    <div className="text-sm font-medium text-slate-900 mb-1 truncate">{clienti[l.cliente_id] || "—"}</div>
                    <div className="text-xs text-slate-500 truncate">{articoli[l.articolo_id]?.descrizione}</div>
                    <div className="mt-2 pt-2 border-t border-slate-100 flex items-center justify-between text-xs">
                      <span className="font-mono text-slate-500">{l.quantita} pz · {l.peso} kg</span>
                      {NEXT_STATE[col.key] && (
                        <button
                          onClick={() => moveTo(l.id, NEXT_STATE[col.key])}
                          className="text-indaco hover:bg-indaco hover:text-white rounded p-1 transition-colors"
                          title={`Avanza a ${NEXT_STATE[col.key]}`}
                          data-testid={`advance-${l.numero}`}
                        >
                          <ArrowRight size={14} weight="bold" />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
                {items.length === 0 && <div className="text-center py-8 text-xs text-slate-400">Nessun lotto</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
