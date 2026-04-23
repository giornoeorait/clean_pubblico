import React, { useEffect, useState } from "react";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useNavigate } from "react-router-dom";
import StatoBadge from "../components/StatoBadge";
import { Storefront, Receipt, Package, Truck, SignOut, House, Warning } from "@phosphor-icons/react";

export default function Portale() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [lotti, setLotti] = useState([]);
  const [consegne, setConsegne] = useState([]);
  const [fatture, setFatture] = useState([]);

  useEffect(() => {
    (async () => {
      const [l, c, f] = await Promise.all([api.get("/lotti?limit=100"), api.get("/consegne"), api.get("/fatture")]);
      setLotti(l.data); setConsegne(c.data); setFatture(f.data);
    })();
  }, []);

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-celeste to-indaco flex items-center justify-center">
            <Storefront size={20} weight="duotone" className="text-white" />
          </div>
          <div>
            <div className="overline">Portale Cliente</div>
            <div className="font-display font-bold text-lg text-slate-900">CleanTec</div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-sm">
            <div className="font-semibold text-slate-900">{user.name}</div>
            <div className="text-xs text-slate-500 font-mono">{user.email}</div>
          </div>
          <button onClick={() => nav("/dashboard")} className="w-10 h-10 bg-slate-100 rounded-lg flex items-center justify-center"><House size={18} /></button>
          <button onClick={async () => { await logout(); nav("/login"); }} className="w-10 h-10 bg-slate-100 rounded-lg flex items-center justify-center"><SignOut size={18} /></button>
        </div>
      </header>

      <main className="max-w-6xl mx-auto p-8">
        <div className="mb-8">
          <div className="overline">Area Riservata</div>
          <h1 className="font-display text-3xl font-bold mt-1">Storico e documenti</h1>
          <p className="text-slate-500 mt-1">Consulta i tuoi ritiri, consegne, fatture e contestazioni.</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <div className="kpi-card"><div className="flex items-center gap-3"><div className="w-10 h-10 rounded-lg bg-indaco/10 flex items-center justify-center"><Package size={20} className="text-indaco" weight="duotone" /></div><div><div className="overline">Lotti in lavorazione</div><div className="font-display text-2xl font-bold">{lotti.filter(l => l.stato_corrente !== "consegnato").length}</div></div></div></div>
          <div className="kpi-card"><div className="flex items-center gap-3"><div className="w-10 h-10 rounded-lg bg-azzurro/10 flex items-center justify-center"><Truck size={20} className="text-azzurro" weight="duotone" /></div><div><div className="overline">Consegne previste</div><div className="font-display text-2xl font-bold">{consegne.filter(c => c.stato !== "consegnata").length}</div></div></div></div>
          <div className="kpi-card"><div className="flex items-center gap-3"><div className="w-10 h-10 rounded-lg bg-emerald-100 flex items-center justify-center"><Receipt size={20} className="text-emerald-600" weight="duotone" /></div><div><div className="overline">Fatture</div><div className="font-display text-2xl font-bold">{fatture.length}</div></div></div></div>
          <div className="kpi-card"><div className="flex items-center gap-3"><div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center"><Warning size={20} className="text-amber-600" weight="duotone" /></div><div><div className="overline">Contestazioni aperte</div><div className="font-display text-2xl font-bold">0</div></div></div></div>
        </div>

        <div className="kpi-card mb-6">
          <div className="font-display font-bold text-xl mb-4">Ultimi lotti</div>
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead><tr><th>Lotto</th><th>Quantità</th><th>Peso</th><th>Stato</th><th>Aggiornato</th></tr></thead>
              <tbody>
                {lotti.slice(0, 10).map(l => (
                  <tr key={l.id}>
                    <td className="font-mono text-xs font-bold text-indaco">{l.numero}</td>
                    <td className="font-mono">{l.quantita}</td>
                    <td className="font-mono">{l.peso} kg</td>
                    <td><StatoBadge stato={l.stato_corrente} /></td>
                    <td className="text-xs font-mono text-slate-500">{new Date(l.created_at).toLocaleDateString("it-IT")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="kpi-card">
          <div className="font-display font-bold text-xl mb-4">Fatture</div>
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead><tr><th>Numero</th><th>Data</th><th>Totale</th><th>Stato</th></tr></thead>
              <tbody>
                {fatture.map(f => (
                  <tr key={f.id}>
                    <td className="font-mono font-bold text-indaco">{f.numero}</td>
                    <td className="font-mono text-xs">{f.data}</td>
                    <td className="font-mono font-bold">€ {f.totale?.toFixed(2)}</td>
                    <td><StatoBadge stato={f.stato} /></td>
                  </tr>
                ))}
                {fatture.length === 0 && <tr><td colSpan={4} className="text-center py-6 text-slate-400">Nessuna fattura</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </main>
    </div>
  );
}
