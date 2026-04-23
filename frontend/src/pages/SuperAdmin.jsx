import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Switch } from "../components/ui/switch";
import { Buildings, CurrencyEur, TrendUp, Users, Receipt, ChartBar, Crown, Star, Sparkle, CircleNotch, EnvelopeSimple, PaperPlaneTilt, CheckCircle, XCircle, FloppyDisk } from "@phosphor-icons/react";
import { toast } from "sonner";

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

  // SMTP state
  const [smtp, setSmtp] = useState({ host: "", port: 587, username: "", password: "", from_email: "", from_name: "CleanTec", use_tls: true, use_ssl: false, enabled: false });
  const [smtpStatus, setSmtpStatus] = useState({ configured: false, password_set: false });
  const [testTo, setTestTo] = useState("");
  const [savingSmtp, setSavingSmtp] = useState(false);
  const [testingSmtp, setTestingSmtp] = useState(false);
  const [emailEvents, setEmailEvents] = useState([]);

  const fetchAll = useCallback(async () => {
    try {
      const [s, t, x, sm, ev] = await Promise.all([
        api.get("/admin/stats"),
        api.get("/admin/tenants"),
        api.get("/admin/transactions"),
        api.get("/admin/smtp-config"),
        api.get("/admin/email-events?limit=20").catch(() => ({ data: [] })),
      ]);
      setStats(s.data); setTenants(t.data); setTxs(x.data);
      setSmtpStatus({ configured: sm.data.configured, password_set: sm.data.password_set });
      setSmtp({
        host: sm.data.host || "",
        port: sm.data.port || 587,
        username: sm.data.username || "",
        password: "",
        from_email: sm.data.from_email || "",
        from_name: sm.data.from_name || "CleanTec",
        use_tls: sm.data.use_tls !== false,
        use_ssl: !!sm.data.use_ssl,
        enabled: !!sm.data.enabled,
      });
      setEmailEvents(ev.data);
    } catch (e) { /* no-op */ }
    setLoading(false);
  }, []);

  const saveSmtp = async () => {
    setSavingSmtp(true);
    try {
      const payload = { ...smtp };
      if (!payload.password) delete payload.password; // keep existing
      await api.patch("/admin/smtp-config", payload);
      toast.success("Configurazione SMTP salvata");
      fetchAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore salvataggio");
    }
    setSavingSmtp(false);
  };

  const testSmtp = async () => {
    if (!testTo) { toast.error("Inserisci email destinataria di test"); return; }
    setTestingSmtp(true);
    try {
      const { data } = await api.post("/admin/smtp-test", { to: testTo });
      if (data.status === "sent") toast.success(`Email di test inviata a ${testTo}`);
      else toast.error(`Invio fallito: ${data.error || "errore sconosciuto"}`);
      fetchAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore test");
    }
    setTestingSmtp(false);
  };

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

      {/* SMTP Configuration */}
      <div className="kpi-card mb-6" data-testid="smtp-card">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <EnvelopeSimple size={22} className="text-indaco" weight="duotone" />
            <h3 className="font-display text-lg font-bold">Server SMTP (email uscenti)</h3>
          </div>
          <div className={`px-3 py-1 rounded-full text-xs font-bold ${smtpStatus.configured ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>
            {smtpStatus.configured ? "ATTIVO" : "NON CONFIGURATO"}
          </div>
        </div>
        <p className="text-sm text-slate-500 mb-4">
          Configura il tuo server SMTP per inviare email di verifica, notifiche e reset password. Quando disattivato, le email vengono solo loggate (stub).
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <Label>Host SMTP *</Label>
            <Input value={smtp.host} onChange={e => setSmtp({...smtp, host: e.target.value})} placeholder="smtp.gmail.com" data-testid="smtp-host" />
          </div>
          <div>
            <Label>Porta *</Label>
            <Input type="number" value={smtp.port} onChange={e => setSmtp({...smtp, port: parseInt(e.target.value) || 587})} placeholder="587" data-testid="smtp-port" />
          </div>
          <div>
            <Label>Username / email auth</Label>
            <Input value={smtp.username} onChange={e => setSmtp({...smtp, username: e.target.value})} placeholder="noreply@tuodominio.it" data-testid="smtp-username" />
          </div>
          <div>
            <Label>Password {smtpStatus.password_set && <span className="text-xs text-emerald-600 font-mono ml-2">• salvata (lascia vuoto per non cambiare)</span>}</Label>
            <Input type="password" value={smtp.password} onChange={e => setSmtp({...smtp, password: e.target.value})} placeholder={smtpStatus.password_set ? "•••••••• (non modificare)" : "password o app password"} data-testid="smtp-password" />
          </div>
          <div>
            <Label>From email *</Label>
            <Input type="email" value={smtp.from_email} onChange={e => setSmtp({...smtp, from_email: e.target.value})} placeholder="noreply@tuodominio.it" data-testid="smtp-from-email" />
          </div>
          <div>
            <Label>From name</Label>
            <Input value={smtp.from_name} onChange={e => setSmtp({...smtp, from_name: e.target.value})} placeholder="CleanTec" data-testid="smtp-from-name" />
          </div>
        </div>

        <div className="flex items-center gap-6 mb-4">
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <Switch checked={smtp.use_tls} onCheckedChange={v => setSmtp({...smtp, use_tls: v, use_ssl: v ? false : smtp.use_ssl})} data-testid="smtp-use-tls" />
            <span>STARTTLS (porta 587)</span>
          </label>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <Switch checked={smtp.use_ssl} onCheckedChange={v => setSmtp({...smtp, use_ssl: v, use_tls: v ? false : smtp.use_tls})} data-testid="smtp-use-ssl" />
            <span>SSL/TLS (porta 465)</span>
          </label>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <Switch checked={smtp.enabled} onCheckedChange={v => setSmtp({...smtp, enabled: v})} data-testid="smtp-enabled" />
            <span className={`font-semibold ${smtp.enabled ? "text-emerald-700" : "text-slate-500"}`}>Abilitato</span>
          </label>
        </div>

        <div className="flex flex-wrap gap-2 items-end">
          <Button onClick={saveSmtp} disabled={savingSmtp} className="bg-indaco hover:bg-indaco-dark" data-testid="smtp-save-btn">
            <FloppyDisk size={16} className="mr-1" />{savingSmtp ? "Salvataggio…" : "Salva configurazione"}
          </Button>
          <div className="flex-1 min-w-[200px] flex gap-2">
            <Input type="email" value={testTo} onChange={e => setTestTo(e.target.value)} placeholder="Email destinataria test..." className="flex-1" data-testid="smtp-test-to" />
            <Button onClick={testSmtp} disabled={!smtpStatus.configured || testingSmtp} variant="outline" data-testid="smtp-test-btn">
              <PaperPlaneTilt size={14} className="mr-1" />{testingSmtp ? "Invio…" : "Invia test"}
            </Button>
          </div>
        </div>

        {emailEvents.length > 0 && (
          <div className="mt-6 pt-4 border-t border-slate-200">
            <div className="overline mb-2">Ultime email inviate</div>
            <div className="space-y-1.5 max-h-64 overflow-y-auto">
              {emailEvents.map(ev => (
                <div key={ev.id} className="flex items-center gap-2 text-xs py-1.5 px-2 rounded hover:bg-slate-50" data-testid={`email-event-${ev.id}`}>
                  {ev.status === "sent" ? <CheckCircle size={14} weight="fill" className="text-emerald-500 flex-shrink-0" /> : ev.status === "failed" ? <XCircle size={14} weight="fill" className="text-red-500 flex-shrink-0" /> : <CircleNotch size={14} className="text-slate-400 flex-shrink-0" />}
                  <span className="font-mono text-slate-600">{ev.to}</span>
                  <span className="flex-1 truncate text-slate-500">{ev.subject}</span>
                  <span className="text-slate-400 font-mono">{new Date(ev.created_at).toLocaleString("it-IT", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span>
                  <span className={`text-[10px] uppercase tracking-widest font-bold ${ev.status === "sent" ? "text-emerald-600" : ev.status === "failed" ? "text-red-600" : "text-slate-400"}`}>{ev.provider}/{ev.status}</span>
                </div>
              ))}
            </div>
          </div>
        )}
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
