import React, { useEffect, useState } from "react";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useNavigate } from "react-router-dom";
import { Truck, MapPin, Camera, PencilSimpleLine, CheckCircle, SignOut, House, Phone, Package } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function Mobile() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [consegne, setConsegne] = useState([]);
  const [clienti, setClienti] = useState({});

  const fetch = async () => {
    const [c, cli] = await Promise.all([api.get("/consegne"), api.get("/clienti")]);
    setConsegne(c.data);
    const m = {}; cli.data.forEach(x => m[x.id] = x); setClienti(m);
  };
  useEffect(() => { fetch(); }, []);

  const marcaConsegnata = async (id) => {
    const c = consegne.find(x => x.id === id);
    await api.patch(`/consegne/${id}`, { stato: "consegnata" });
    if (c?.lotti_ids) for (const lid of c.lotti_ids) await api.post(`/lotti/${lid}/cambia-stato`, { nuovo_stato: "consegnato" });
    toast.success("Consegna confermata");
    fetch();
  };

  const attive = consegne.filter(c => c.stato === "pianificata" || c.stato === "in_consegna");

  return (
    <div className="min-h-screen bg-slate-50 max-w-md mx-auto shadow-xl">
      <header className="sticky top-0 bg-indaco text-white px-5 py-4 flex items-center justify-between shadow-md z-10">
        <div>
          <div className="text-xs text-celeste font-mono uppercase tracking-widest">App Autista</div>
          <div className="font-display font-bold text-lg">Ciao, {user.name?.split(" ")[0]}</div>
        </div>
        <div className="flex gap-2">
          <button onClick={() => nav("/dashboard")} className="w-10 h-10 bg-white/10 rounded-lg flex items-center justify-center"><House size={18} /></button>
          <button onClick={async () => { await logout(); nav("/login"); }} className="w-10 h-10 bg-white/10 rounded-lg flex items-center justify-center"><SignOut size={18} /></button>
        </div>
      </header>

      <div className="p-5">
        <div className="bg-gradient-to-br from-indaco to-indaco-dark text-white rounded-2xl p-5 shadow-lg mb-5">
          <div className="text-xs uppercase tracking-widest text-celeste mb-1">Giro odierno</div>
          <div className="font-display text-4xl font-bold">{attive.length}</div>
          <div className="text-sm text-white/70 mt-1">consegne in programma</div>
        </div>

        <div className="space-y-3">
          {attive.map(c => {
            const cliente = clienti[c.cliente_id];
            return (
              <div key={c.id} className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm" data-testid={`mob-${c.numero}`}>
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <div className="font-mono text-xs text-indaco font-bold">{c.numero}</div>
                    <div className="font-display font-bold text-lg mt-0.5">{cliente?.ragione_sociale}</div>
                  </div>
                  <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded ${c.stato === "in_consegna" ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-600"}`}>
                    {c.stato}
                  </span>
                </div>
                {cliente && (
                  <>
                    <div className="flex items-start gap-2 text-sm text-slate-600 mb-2">
                      <MapPin size={16} className="text-indaco flex-shrink-0 mt-0.5" weight="duotone" />
                      <span>{cliente.indirizzo}</span>
                    </div>
                    {cliente.telefono && (
                      <a href={`tel:${cliente.telefono}`} className="flex items-center gap-2 text-sm text-indaco mb-3">
                        <Phone size={16} weight="duotone" />
                        <span className="font-mono">{cliente.telefono}</span>
                      </a>
                    )}
                  </>
                )}
                <div className="flex items-center gap-2 text-xs text-slate-500 py-2 border-t border-slate-100">
                  <Package size={14} />
                  <span>{c.lotti_ids?.length || 0} lotti · data {(c.data_prevista || "").slice(0,10)}</span>
                </div>
                <div className="grid grid-cols-3 gap-2 mt-3">
                  <button className="py-3 bg-slate-100 text-slate-700 rounded-lg flex flex-col items-center gap-1 text-xs font-medium active:bg-slate-200"><Camera size={18} weight="duotone" />Foto</button>
                  <button className="py-3 bg-slate-100 text-slate-700 rounded-lg flex flex-col items-center gap-1 text-xs font-medium active:bg-slate-200"><PencilSimpleLine size={18} weight="duotone" />Firma</button>
                  <button
                    onClick={() => marcaConsegnata(c.id)}
                    className="py-3 bg-emerald-500 text-white rounded-lg flex flex-col items-center gap-1 text-xs font-bold active:bg-emerald-600"
                    data-testid={`mob-confirm-${c.numero}`}
                  >
                    <CheckCircle size={18} weight="bold" />Conferma
                  </button>
                </div>
              </div>
            );
          })}
          {attive.length === 0 && <div className="text-center py-12 text-slate-400">Nessuna consegna in programma</div>}
        </div>
      </div>
    </div>
  );
}
