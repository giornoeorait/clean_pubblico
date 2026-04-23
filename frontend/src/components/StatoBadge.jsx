import React from "react";

const COLORS = {
  ritirato: "bg-slate-100 text-slate-700 border border-slate-200",
  ricevuto: "bg-sky-50 text-sky-700 border border-sky-200",
  smistato: "bg-sky-100 text-sky-800 border border-sky-200",
  lavato: "bg-blue-100 text-blue-800 border border-blue-200",
  asciugato: "bg-cyan-100 text-cyan-800 border border-cyan-200",
  stirato: "bg-indigo-100 text-indigo-800 border border-indigo-200",
  confezionato: "bg-violet-100 text-violet-800 border border-violet-200",
  pronto: "bg-emerald-100 text-emerald-800 border border-emerald-200",
  consegnato: "bg-emerald-600 text-white border border-emerald-700",
  aperta: "bg-red-100 text-red-800 border border-red-200",
  in_lavorazione: "bg-amber-100 text-amber-800 border border-amber-200",
  risolta: "bg-emerald-100 text-emerald-800 border border-emerald-200",
  pianificata: "bg-slate-100 text-slate-700 border border-slate-200",
  in_consegna: "bg-amber-100 text-amber-800 border border-amber-200",
  consegnata: "bg-emerald-100 text-emerald-800 border border-emerald-200",
  contestata: "bg-red-100 text-red-800 border border-red-200",
  bozza: "bg-slate-100 text-slate-700 border border-slate-200",
  emessa: "bg-sky-100 text-sky-800 border border-sky-200",
  pagata: "bg-emerald-100 text-emerald-800 border border-emerald-200",
  scaduta: "bg-red-100 text-red-800 border border-red-200",
  disponibile: "bg-emerald-100 text-emerald-800 border border-emerald-200",
  in_uso: "bg-azzurro/10 text-azzurro border border-azzurro/30",
  guasto: "bg-red-100 text-red-800 border border-red-200",
  manutenzione: "bg-amber-100 text-amber-800 border border-amber-200",
  normale: "bg-slate-100 text-slate-700 border border-slate-200",
  alta: "bg-amber-100 text-amber-800 border border-amber-200",
  urgente: "bg-red-100 text-red-800 border border-red-200",
  creato: "bg-slate-100 text-slate-700 border border-slate-200",
  pending: "bg-slate-100 text-slate-700 border border-slate-200",
  in_corso: "bg-azzurro/10 text-azzurro border border-azzurro/30",
  completato: "bg-emerald-100 text-emerald-800 border border-emerald-200",
};

export default function StatoBadge({ stato, children }) {
  const cls = COLORS[stato] || "bg-slate-100 text-slate-700 border border-slate-200";
  return (
    <span className={`stato-pill ${cls}`} data-testid={`stato-${stato}`}>
      {children || (stato ? stato.replace(/_/g, " ") : "—")}
    </span>
  );
}
