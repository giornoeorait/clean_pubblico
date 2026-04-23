import React, { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Crown, CheckCircle, ClockCountdown, Warning, CreditCard, ArrowRight, Star, Sparkle } from "@phosphor-icons/react";
import { toast } from "sonner";

const PLAN_ICON = { starter: Star, pro: Crown, enterprise: Sparkle };

const STATO_BADGE = {
  trial: "bg-amber-100 text-amber-700 border border-amber-200",
  active: "bg-emerald-100 text-emerald-700 border border-emerald-200",
  past_due: "bg-red-100 text-red-700 border border-red-200",
  canceled: "bg-slate-100 text-slate-700 border border-slate-200",
  suspended: "bg-red-100 text-red-700 border border-red-200",
};

export default function Billing() {
  const [sp] = useSearchParams();
  const [data, setData] = useState(null);
  const [plans, setPlans] = useState([]);
  const [txs, setTxs] = useState([]);
  const [selectedPlan, setSelectedPlan] = useState("pro");
  const [cycle, setCycle] = useState("monthly");
  const [busy, setBusy] = useState(false);

  const fetchAll = useCallback(async () => {
    const [me, pl, t] = await Promise.all([
      api.get("/tenants/me"),
      api.get("/plans"),
      api.get("/subscriptions/transactions").catch(() => ({ data: [] })),
    ]);
    setData(me.data); setPlans(pl.data.plans); setTxs(t.data);
    if (me.data?.tenant?.piano) setSelectedPlan(me.data.tenant.piano);
    if (me.data?.tenant?.billing_cycle) setCycle(me.data.tenant.billing_cycle);
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  // Handle return from Stripe
  useEffect(() => {
    const sid = sp.get("session_id");
    if (sid) {
      (async () => {
        toast.loading("Verifica pagamento…", { id: "pay" });
        let attempts = 0;
        const poll = async () => {
          attempts++;
          try {
            const { data: s } = await api.get(`/subscriptions/status/${sid}`);
            if (s.payment_status === "paid") {
              toast.success("Abbonamento attivato! 🎉", { id: "pay" });
              fetchAll();
              return;
            }
            if (s.status === "expired" || attempts > 6) {
              toast.error("Sessione scaduta. Riprova.", { id: "pay" });
              return;
            }
            setTimeout(poll, 2500);
          } catch {
            toast.error("Errore verifica pagamento", { id: "pay" });
          }
        };
        poll();
      })();
    }
    if (sp.get("canceled")) {
      toast.info("Pagamento annullato");
    }
  }, [sp, fetchAll]);

  const startCheckout = async () => {
    setBusy(true);
    try {
      const { data: res } = await api.post("/subscriptions/checkout", {
        plan_id: selectedPlan,
        billing_cycle: cycle,
        origin_url: window.location.origin,
      });
      window.location.href = res.url;
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore checkout");
      setBusy(false);
    }
  };

  if (!data) return <div className="p-8 text-slate-400">Caricamento…</div>;

  const t = data.tenant;
  const plan = data.plan;
  const daysLeft = data.trial_days_left;
  const inTrial = t.stato === "trial";
  const Icon = PLAN_ICON[t.piano] || Star;

  return (
    <div>
      <PageHeader
        eyebrow="Abbonamento"
        title="Billing & Piano"
        subtitle="Gestisci il tuo abbonamento CleanTec e consulta lo storico dei pagamenti."
      />

      {/* Current status card */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="kpi-card col-span-1 md:col-span-2 bg-gradient-to-br from-indaco to-slate-900 text-white border-0">
          <div className="flex items-start justify-between">
            <div>
              <div className="overline text-celeste mb-1">Piano attivo</div>
              <div className="flex items-center gap-3 mb-2">
                <Icon size={32} weight="duotone" className="text-celeste" />
                <div>
                  <div className="font-display text-3xl font-bold capitalize">{plan.nome}</div>
                  <div className={`stato-pill inline-flex mt-1 ${STATO_BADGE[t.stato] || STATO_BADGE.trial}`} data-testid="billing-status">
                    {t.stato === "trial" ? "TRIAL" : t.stato === "active" ? "ATTIVO" : t.stato.toUpperCase()}
                  </div>
                </div>
              </div>
              {inTrial && (
                <div className="flex items-center gap-2 text-amber-300 text-sm">
                  <ClockCountdown size={16} weight="fill" />
                  <span><strong>{daysLeft}</strong> giorni rimanenti di prova</span>
                </div>
              )}
              {t.current_period_end && !inTrial && (
                <div className="text-slate-300 text-sm mt-1">
                  Rinnovo previsto: {new Date(t.current_period_end).toLocaleDateString("it-IT", { day: "numeric", month: "long", year: "numeric" })}
                </div>
              )}
            </div>
            <div className="text-right">
              <div className="font-display text-5xl font-bold">€{cycle === "annual" ? plan.price_annual : plan.price_monthly}</div>
              <div className="text-xs text-slate-300">/mese {cycle === "annual" && "(annuale)"}</div>
            </div>
          </div>
        </div>

        <div className="kpi-card">
          <div className="overline mb-3">Utilizzo</div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between"><span>Utenti</span><span className="font-mono font-bold">{t.usage?.users || 1}{plan.limits.users !== -1 && `/${plan.limits.users}`}</span></div>
            <div className="flex justify-between"><span>Lotti mese</span><span className="font-mono font-bold">{t.usage?.lotti_this_month || 0}{plan.limits.lotti_monthly !== -1 && `/${plan.limits.lotti_monthly}`}</span></div>
            <div className="flex justify-between"><span>SMS inclusi</span><span className="font-mono font-bold">{plan.limits.sms_monthly === 0 ? "—" : `0/${plan.limits.sms_monthly}`}</span></div>
          </div>
        </div>
      </div>

      {/* Upgrade section */}
      {(inTrial || t.stato !== "active" || t.piano !== "enterprise") && (
        <div className="kpi-card mb-6" data-testid="upgrade-card">
          <div className="flex items-center gap-2 mb-4">
            <CreditCard size={22} className="text-indaco" weight="duotone" />
            <h3 className="font-display text-xl font-bold">{inTrial ? "Attiva l'abbonamento" : "Cambia piano"}</h3>
          </div>
          <p className="text-sm text-slate-600 mb-4">
            {inTrial
              ? "Sblocca CleanTec per sempre. Paga ora e mantieni tutti i dati che hai già inserito."
              : "Aggiorna o cambia piano in qualsiasi momento. I crediti non utilizzati vengono proporzionalmente rimborsati."}
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
            <div>
              <label className="text-xs font-semibold uppercase tracking-widest text-slate-500 mb-1 block">Piano</label>
              <Select value={selectedPlan} onValueChange={setSelectedPlan}>
                <SelectTrigger data-testid="billing-plan-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {plans.filter(p => p.id !== "enterprise").map(p => (
                    <SelectItem key={p.id} value={p.id}>{p.nome} — €{p.price_monthly}/mese</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-xs font-semibold uppercase tracking-widest text-slate-500 mb-1 block">Ciclo fatturazione</label>
              <Select value={cycle} onValueChange={setCycle}>
                <SelectTrigger data-testid="billing-cycle-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="monthly">Mensile</SelectItem>
                  <SelectItem value="annual">Annuale (-17%)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end">
              <Button onClick={startCheckout} disabled={busy} className="w-full bg-indaco hover:bg-indaco-dark h-10" data-testid="start-checkout-btn">
                <CreditCard size={16} className="mr-2" />
                {busy ? "Redirect…" : "Vai al pagamento"}
              </Button>
            </div>
          </div>
          <p className="text-xs text-slate-500 flex items-center gap-1">
            <CheckCircle size={12} weight="fill" className="text-emerald-500" />
            Pagamento sicuro via Stripe. Puoi cancellare in qualsiasi momento.
          </p>
        </div>
      )}

      {/* Transactions history */}
      <div className="kpi-card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-display text-lg font-bold">Storico pagamenti</h3>
          <span className="text-xs text-slate-400 font-mono">{txs.length} transazioni</span>
        </div>
        {txs.length === 0 ? (
          <div className="text-center py-8 text-slate-400 text-sm">Nessuna transazione</div>
        ) : (
          <div className="space-y-2">
            {txs.map(tx => (
              <div key={tx.id} className="flex items-center gap-3 py-2 border-b border-slate-100 last:border-0">
                <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${tx.payment_status === "paid" ? "bg-emerald-100 text-emerald-600" : tx.payment_status === "pending" ? "bg-amber-100 text-amber-600" : "bg-slate-100 text-slate-500"}`}>
                  {tx.payment_status === "paid" ? <CheckCircle size={18} weight="duotone" /> : <ClockCountdown size={18} weight="duotone" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-bold capitalize">{tx.plan_id} · {tx.billing_cycle}</div>
                  <div className="text-xs text-slate-500 font-mono">{new Date(tx.created_at).toLocaleString("it-IT")}</div>
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

      {/* Cancel / Resume subscription */}
      {(t.stato === "active" || t.stato === "canceled") && (
        <div className="kpi-card mt-6 border-red-100" data-testid="billing-cancel-card">
          <h3 className="font-display text-lg font-bold mb-2">{t.stato === "canceled" ? "Riattiva abbonamento" : "Cancella abbonamento"}</h3>
          <p className="text-sm text-slate-600 mb-3">
            {t.stato === "canceled"
              ? "Il tuo abbonamento è cancellato ma mantieni l'accesso fino a scadenza periodo. Riattiva per continuare senza interruzione."
              : "Puoi cancellare in qualsiasi momento. Manterrai l'accesso fino alla scadenza del periodo già pagato, poi l'account verrà sospeso."}
          </p>
          {t.stato === "canceled" ? (
            <button
              onClick={async () => {
                try { await api.post("/subscriptions/resume"); toast.success("Abbonamento riattivato"); fetchAll(); }
                catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
              }}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-md font-semibold text-sm"
              data-testid="resume-btn"
            >Riattiva abbonamento</button>
          ) : (
            <button
              onClick={async () => {
                if (!window.confirm("Confermi la cancellazione? Manterrai l'accesso fino alla scadenza del periodo.")) return;
                try { await api.post("/subscriptions/cancel"); toast.info("Abbonamento cancellato"); fetchAll(); }
                catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
              }}
              className="px-4 py-2 bg-white border border-red-300 hover:bg-red-50 text-red-700 rounded-md font-semibold text-sm"
              data-testid="cancel-btn"
            >Cancella abbonamento</button>
          )}
        </div>
      )}
    </div>
  );
}
