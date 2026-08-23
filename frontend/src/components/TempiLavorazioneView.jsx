import React from "react";
import { Trophy, Lightning, Timer, User } from "@phosphor-icons/react";

const fmtMin = (m) => {
  if (m == null) return "—";
  if (m < 60) return `${Math.round(m)} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${Math.round(m % 60)}m`;
  return `${Math.floor(h / 24)}g ${h % 24}h`;
};
const fmtDT = (iso) => iso ? new Date(iso).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";

function Kpi({ label, value, sub, color = "text-indaco" }) {
  return (
    <div className="kpi-card p-4">
      <div className="text-[11px] uppercase tracking-wide text-slate-500 font-mono">{label}</div>
      <div className={`text-2xl md:text-3xl font-display font-bold ${color}`}>{value}</div>
      {sub && <div className="text-xs text-slate-400 mt-1">{sub}</div>}
    </div>
  );
}

function Leaderboard({ title, icon: Icon, rows, metric, testid }) {
  return (
    <div className="kpi-card p-4" data-testid={testid}>
      <h4 className="font-display font-bold text-sm mb-3 flex items-center gap-2"><Icon size={18} className="text-indaco" />{title}</h4>
      {rows.length === 0 && <div className="text-xs text-slate-400">Nessun dato operatore nel periodo</div>}
      <div className="space-y-2">
        {rows.slice(0, 8).map((e, i) => (
          <div key={e.operatore} className="flex items-center gap-3 text-sm">
            <span className={`w-7 h-7 rounded-full flex items-center justify-center font-bold text-xs flex-shrink-0 ${i === 0 ? "bg-amber-100 text-amber-700" : i === 1 ? "bg-slate-200 text-slate-600" : i === 2 ? "bg-orange-100 text-orange-700" : "bg-slate-100 text-slate-500"}`}>{i + 1}</span>
            <span className="flex-1 font-medium truncate flex items-center gap-1.5"><User size={14} className="text-slate-400" />{e.operatore}</span>
            <span className="font-mono text-indaco font-semibold">{metric(e)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function TempiLavorazioneView({ d }) {
  const k = d.kpi || {};
  return (
    <div className="space-y-6" data-testid="tempi-view">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Kpi label="Ordini chiusi" value={k.n_ordini_chiusi ?? 0} sub={k.n_senza_tracking ? `${k.n_senza_tracking} senza tracciamento tempi` : null} />
        <Kpi label="Attesa media (arrivo → presa in carico)" value={fmtMin(k.attesa_media_min)} color="text-amber-600" />
        <Kpi label="Lavorazione media" value={fmtMin(k.lavorazione_media_min)} color="text-emerald-600" />
        <Kpi label="Min / Max lavorazione" value={`${fmtMin(k.lavorazione_min_min)} · ${fmtMin(k.lavorazione_max_min)}`} color="text-sky-600" />
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <Leaderboard title="Operatori più veloci (tempo medio)" icon={Lightning}
          rows={d.classifica_veloci || []} testid="classifica-veloci"
          metric={(e) => `${fmtMin(e.tempo_medio_min)} · ${e.n_ordini} ordini`} />
        <Leaderboard title="Operatori che lavorano di più" icon={Trophy}
          rows={d.classifica_attivi || []} testid="classifica-attivi"
          metric={(e) => `${e.n_ordini} ordini · ${fmtMin(e.tempo_totale_min)} tot`} />
      </div>

      <div className="kpi-card p-4 overflow-x-auto">
        <h4 className="font-display font-bold text-sm mb-3 flex items-center gap-2"><Timer size={18} className="text-indaco" />Dettaglio ordini chiusi</h4>
        <table className="w-full text-sm" data-testid="tempi-table">
          <thead className="text-xs uppercase tracking-wide text-slate-500 border-b border-slate-200">
            <tr>
              <th className="p-2 text-left">Ordine</th><th className="p-2 text-left">Cliente</th>
              <th className="p-2 text-left">Operatore</th><th className="p-2 text-left">Arrivo</th>
              <th className="p-2 text-left">Presa in carico</th><th className="p-2 text-left">Chiusura</th>
              <th className="p-2 text-right">Attesa</th><th className="p-2 text-right">Lavorazione</th>
              <th className="p-2 text-right">Pezzi</th>
            </tr>
          </thead>
          <tbody>
            {(d.ordini || []).map(o => (
              <tr key={o.numero} className="border-b border-slate-100 hover:bg-slate-50">
                <td className="p-2 font-mono text-xs">{o.numero}<div className="text-slate-400">{o.ddt_numero}</div></td>
                <td className="p-2">{o.cliente}</td>
                <td className="p-2 font-medium">{o.operatore || <span className="text-slate-300">—</span>}</td>
                <td className="p-2 font-mono text-xs">{fmtDT(o.arrivo)}</td>
                <td className="p-2 font-mono text-xs">{fmtDT(o.presa_in_carico)}</td>
                <td className="p-2 font-mono text-xs">{fmtDT(o.chiusura)}</td>
                <td className="p-2 text-right font-mono text-amber-600">{fmtMin(o.attesa_min)}</td>
                <td className="p-2 text-right font-mono text-emerald-600 font-semibold">{fmtMin(o.lavorazione_min)}</td>
                <td className="p-2 text-right font-mono">{o.pezzi}</td>
              </tr>
            ))}
            {(d.ordini || []).length === 0 && <tr><td colSpan={9} className="p-6 text-center text-slate-400 text-xs">Nessun ordine chiuso nel periodo</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
