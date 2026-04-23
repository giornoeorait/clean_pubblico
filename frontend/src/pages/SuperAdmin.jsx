import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Buildings, CurrencyEur, TrendUp, Users, Receipt, ChartBar, Crown, Star, Sparkle, CircleNotch } from "@phosphor-icons/react";

const PLAN_COLOR = { starter: "bg-slate-100 text-slate-700", pro: "bg-indaco/10 text-indaco", enterprise: "bg-amber-100 text-amber-700" };
const STATO_COLOR = {
  trial: "bg-amber-100 text-amber-700",
  active: "bg-emerald-100 text-emerald-700",
  canceled: "bg-slate-100 text-slate-600",
  past_due: "bg-red-100 text-red-700",
  suspended: "bg-red-100 text-red-700",
};

export default function SuperAdmin() {
  const [stats, setStats] = useState(null);
  const [tenants, setTenants] = useState([]);
  const [txs, setTxs] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(async () => {
    try {
      const [s, t, x] = await Promise.all([
        api.get("/admin/stats"),
        api.get("/admin/tenants"),
        api.get("/admin/transactions"),
      ]);
      setStats(s.data); setTenants(t.data); setTxs(x.data);
    } catch (e) { /* no-op */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  if (loading) return <div className="p-8 text-slate-400 flex items-center gap-2"><CircleNotch className="animate-spin" /> Caricamento…</div>;
  if (!stats) return <div className="p-8 text-red-600">Accesso negato (solo superadmin)</div>;

  const cards = [
    { label: "MRR", value: `€ ${stats.mrr.toLocaleString("it-IT")}`, sub: `ARR €${stats.arr.toLocaleString("it-IT")}`, icon: CurrencyEur, color: "bg-emerald-500" },
    { label: "Tenants totali", value: stats.total_tenants, sub: `${stats.new_signups_month} nuovi questo mese`, icon: Buildings, color: "bg-indaco" },
    { label: "Conversione trial 90gg", value: `${stats.trial_conversion_90d_pct}%`, sub: "trial → paid", icon: TrendUp, color: "bg-amber-500" },
    { label: "Incassato questo mese", value: `€ ${stats.revenue_this_month.toLocaleString("it-IT")}`, sub: `${stats.paid_transactions_month} pagamenti`, icon: Receipt, color: "bg-sky-500" },
  ];

  return (
    <div>
      <PageHeader
        eyebrow="Superadmin"
        title="Pannello SaaS"
        subtitle="Metriche globali, lista tenants, transazioni. Solo ruolo superadmin."
      />

      {/* Stats KPI */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {cards.map(c => {
          const Icon = c.icon;
          return (
            <div key={c.label} className="kpi-card" data-testid={`super-kpi-${c.label.toLowerCase().replace(/\s/g,'-')}`}>
              <div className="flex items-start gap-3">
                <div className={`w-11 h-11 rounded-xl ${c.color} flex items-center justify-center text-white`}>
                  <Icon size={22} weight="duotone" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="overline">{c.label}</div>
                  <div className="font-display text-2xl font-bold text-slate-900">{c.value}</div>
                  <div className="text-xs text-slate-500 mt-0.5">{c.sub}</div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Piano & Stato distribution */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <div className="kpi-card">
          <div className="overline mb-3">Distribuzione piani</div>
          <div className="space-y-2">
            {["starter", "pro", "enterprise"].map(p => {
              const cnt = stats.by_piano?.[p] || 0;
              const total = stats.total_tenants || 1;
              return (
                <div key={p} className="flex items-center gap-2 text-sm">
                  <div className="w-16 capitalize font-semibold">{p}</div>
                  <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div className="h-full bg-indaco" style={{ width: `${(cnt/total*100)}%` }}></div>
                  </div>
                  <div className="font-mono text-xs text-slate-500 w-8 text-right">{cnt}</div>
                </div>
              );
            })}
          </div>
        </div>
        <div className="kpi-card">
          <div className="overline mb-3">Distribuzione stati</div>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(stats.by_stato || {}).map(([k, v]) => (
              <div key={k} className={`flex items-center justify-between px-3 py-2 rounded-md text-sm ${STATO_COLOR[k] || "bg-slate-100"}`}>
                <span className="capitalize">{k}</span>
                <span className="font-mono font-bold">{v}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Tenants list */}
      <div className="kpi-card mb-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-display text-lg font-bold">Tenants registrati</h3>
          <span className="text-xs font-mono text-slate-400">{tenants.length}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-widest text-slate-500 border-b border-slate-200">
              <tr>
                <th className="text-left py-2">Azienda</th>
                <th className="text-left py-2">Piano</th>
                <th className="text-left py-2">Stato</th>
                <th className="text-right py-2">Utenti</th>
                <th className="text-right py-2">MRR</th>
                <th className="text-left py-2 pl-3">Ultima attività</th>
              </tr>
            </thead>
            <tbody>
              {tenants.map(t => (
                <tr key={t.id} className="border-b border-slate-100" data-testid={`super-tenant-${t.slug}`}>
                  <td className="py-3">
                    <div className="font-semibold">{t.nome}</div>
                    <div className="text-xs text-slate-500 font-mono">{t.email_admin} · {t.partita_iva || "no P.IVA"}</div>
                  </td>
                  <td><span className={`px-2 py-0.5 text-xs rounded-full capitalize ${PLAN_COLOR[t.piano]}`}>{t.piano}</span></td>
                  <td><span className={`px-2 py-0.5 text-xs rounded-full ${STATO_COLOR[t.stato]}`}>{t.stato}</span></td>
                  <td className="text-right font-mono">{t.users_count}</td>
                  <td className="text-right font-mono">€{t.mrr_contribution.toFixed(0)}</td>
                  <td className="pl-3 text-xs text-slate-500">{t.last_activity ? new Date(t.last_activity).toLocaleDateString("it-IT") : "—"}</td>
                </tr>
              ))}
              {tenants.length === 0 && <tr><td colSpan="6" className="text-center py-8 text-slate-400">Nessun tenant registrato</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {/* Transactions */}
      <div className="kpi-card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-display text-lg font-bold">Ultime transazioni</h3>
          <span className="text-xs font-mono text-slate-400">{txs.length}</span>
        </div>
        {txs.length === 0 ? (
          <div className="text-center py-8 text-slate-400 text-sm">Nessuna transazione</div>
        ) : (
          <div className="space-y-2">
            {txs.slice(0, 20).map(tx => (
              <div key={tx.id} className="flex items-center gap-3 py-2 border-b border-slate-100 last:border-0">
                <div className={`w-2 h-2 rounded-full ${tx.payment_status === "paid" ? "bg-emerald-500" : tx.payment_status === "pending" ? "bg-amber-500" : "bg-slate-300"}`}></div>
                <div className="flex-1 text-sm">
                  <div className="font-mono">{tx.plan_id} · {tx.billing_cycle}</div>
                  <div className="text-xs text-slate-500">{tx.user_email} · {new Date(tx.created_at).toLocaleString("it-IT")}</div>
                </div>
                <div className="text-right">
                  <div className="font-display font-bold">€{tx.amount.toFixed(2)}</div>
                  <div className="text-[10px] uppercase tracking-widest font-mono text-slate-500">{tx.payment_status}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
