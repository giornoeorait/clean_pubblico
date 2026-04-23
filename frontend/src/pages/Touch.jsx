import React, { useEffect, useState } from "react";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useNavigate } from "react-router-dom";
import { Sparkle, SignOut, Scan, Drop, Wind, ShirtFolded, Package, CheckCircle, Truck, House } from "@phosphor-icons/react";
import { toast } from "sonner";

const ACTIONS = [
  { stato: "ricevuto", label: "Ricezione", icon: Package, color: "bg-sky-500" },
  { stato: "smistato", label: "Smistamento", icon: Scan, color: "bg-sky-600" },
  { stato: "lavato", label: "Lavaggio", icon: Drop, color: "bg-blue-500" },
  { stato: "asciugato", label: "Asciugatura", icon: Wind, color: "bg-cyan-500" },
  { stato: "stirato", label: "Stiratura", icon: ShirtFolded, color: "bg-indigo-500" },
  { stato: "confezionato", label: "Confezionamento", icon: Package, color: "bg-violet-500" },
  { stato: "pronto", label: "Pronto", icon: CheckCircle, color: "bg-emerald-500" },
  { stato: "consegnato", label: "Consegnato", icon: Truck, color: "bg-emerald-700" },
];

export default function Touch() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [lotti, setLotti] = useState([]);
  const [selectedLotto, setSelectedLotto] = useState(null);
  const [scanCode, setScanCode] = useState("");

  const fetch = async () => {
    const { data } = await api.get("/lotti?limit=50");
    setLotti(data);
  };
  useEffect(() => { fetch(); const t = setInterval(fetch, 15000); return () => clearInterval(t); }, []);

  const avanza = async (stato) => {
    if (!selectedLotto) return;
    await api.post(`/lotti/${selectedLotto.id}/cambia-stato`, { nuovo_stato: stato });
    toast.success(`${selectedLotto.numero} → ${stato}`);
    setSelectedLotto(null);
    fetch();
  };

  const filtered = scanCode ? lotti.filter(l => l.numero.toLowerCase().includes(scanCode.toLowerCase())) : lotti;

  return (
    <div className="min-h-screen bg-slate-100">
      {/* Header touch */}
      <header className="h-20 bg-indaco text-white flex items-center justify-between px-8 shadow-md">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-white/10 flex items-center justify-center">
            <Sparkle size={22} weight="fill" className="text-celeste" />
          </div>
          <div>
            <div className="font-display font-bold text-xl">CleanTec • Touch</div>
            <div className="text-xs text-celeste font-mono uppercase tracking-widest">Modalità produzione</div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-sm font-semibold">{user.name}</div>
            <div className="text-xs text-celeste font-mono uppercase">{user.role}</div>
          </div>
          <button onClick={() => nav("/dashboard")} className="w-12 h-12 bg-white/10 hover:bg-white/20 rounded-lg flex items-center justify-center transition-colors" data-testid="touch-home"><House size={22} /></button>
          <button onClick={async () => { await logout(); nav("/login"); }} className="w-12 h-12 bg-white/10 hover:bg-white/20 rounded-lg flex items-center justify-center transition-colors" data-testid="touch-logout"><SignOut size={22} /></button>
        </div>
      </header>

      <div className="p-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Scan + Lista lotti */}
        <div className="lg:col-span-1">
          <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200 mb-4">
            <div className="overline mb-2">Scan / Ricerca lotto</div>
            <div className="relative">
              <Scan size={28} className="absolute left-4 top-1/2 -translate-y-1/2 text-indaco" />
              <input
                value={scanCode}
                onChange={e => setScanCode(e.target.value)}
                className="w-full pl-14 pr-4 py-5 text-2xl font-mono border-2 border-slate-200 rounded-xl focus:border-indaco focus:ring-0 outline-none"
                placeholder="LOT-2026-..."
                data-testid="touch-scan-input"
                autoFocus
              />
            </div>
          </div>

          <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200 max-h-[60vh] overflow-y-auto">
            <div className="overline mb-3">Lotti recenti ({filtered.length})</div>
            <div className="space-y-2">
              {filtered.slice(0, 20).map(l => (
                <button
                  key={l.id}
                  onClick={() => setSelectedLotto(l)}
                  data-testid={`touch-lotto-${l.numero}`}
                  className={`w-full text-left p-4 rounded-lg border-2 transition-all ${selectedLotto?.id === l.id ? "border-indaco bg-indaco/5" : "border-slate-200 bg-white hover:border-indaco/40"}`}
                >
                  <div className="font-mono font-bold text-indaco">{l.numero}</div>
                  <div className="text-sm mt-1 flex justify-between">
                    <span className="text-slate-600">{l.quantita} pz · {l.peso} kg</span>
                    <span className="text-xs uppercase font-semibold text-slate-500">{l.stato_corrente}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Azioni touch */}
        <div className="lg:col-span-2">
          <div className="bg-white rounded-xl p-6 shadow-sm border border-slate-200 mb-4">
            <div className="overline mb-2">Lotto selezionato</div>
            {selectedLotto ? (
              <div>
                <div className="font-display font-bold text-3xl text-indaco">{selectedLotto.numero}</div>
                <div className="flex gap-6 mt-3 font-mono text-slate-600">
                  <span>{selectedLotto.quantita} pz</span>
                  <span>{selectedLotto.peso} kg</span>
                  <span className="uppercase">Stato: <b>{selectedLotto.stato_corrente}</b></span>
                </div>
              </div>
            ) : (
              <div className="text-slate-400 text-lg">Scansiona o seleziona un lotto dalla lista</div>
            )}
          </div>

          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {ACTIONS.map(a => (
              <button
                key={a.stato}
                onClick={() => avanza(a.stato)}
                disabled={!selectedLotto}
                data-testid={`touch-btn-${a.stato}`}
                className={`${a.color} text-white rounded-2xl shadow-lg active:translate-y-1 active:scale-95 text-2xl font-bold flex flex-col items-center justify-center gap-3 transition-all h-40 disabled:opacity-30 disabled:cursor-not-allowed hover:brightness-110`}
              >
                <a.icon size={48} weight="duotone" />
                <span className="font-display">{a.label}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
