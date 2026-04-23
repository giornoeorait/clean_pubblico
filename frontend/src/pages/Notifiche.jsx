import React, { useCallback, useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { ChatCircleText, WhatsappLogo, PaperPlaneTilt, CheckCircle, XCircle, Warning, Plus } from "@phosphor-icons/react";
import { toast } from "sonner";

const STATO_CLS = {
  sent: "bg-emerald-100 text-emerald-700 border border-emerald-200",
  logged: "bg-slate-100 text-slate-600 border border-slate-200",
  failed: "bg-red-100 text-red-700 border border-red-200",
  pending: "bg-amber-100 text-amber-700 border border-amber-200",
};

const EMPTY = { kind: "sms", to: "", template: "", body: "", template_vars: "{}" };

export default function Notifiche() {
  const [list, setList] = useState([]);
  const [status, setStatus] = useState({ twilio_enabled: false, templates: [] });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);

  const fetchAll = useCallback(async () => {
    const [l, s] = await Promise.all([api.get("/notifications"), api.get("/notifications/status")]);
    setList(l.data); setStatus(s.data);
  }, []);
  useEffect(() => { fetchAll(); }, [fetchAll]);

  const send = async (e) => {
    e.preventDefault();
    if (!form.to) { toast.error("Destinatario richiesto"); return; }
    if (!form.body && !form.template) { toast.error("Testo o template richiesto"); return; }
    try {
      const payload = {
        kind: form.kind, to: form.to,
        body: form.body || undefined,
        template: form.template || undefined,
        template_vars: form.template ? JSON.parse(form.template_vars || "{}") : undefined,
      };
      const { data } = await api.post("/notifications/send", payload);
      toast.success(`Notifica ${data.status === "sent" ? "inviata" : "registrata (stub)"}`);
      setOpen(false); setForm(EMPTY); fetchAll();
    } catch (e2) {
      toast.error(e2.response?.data?.detail || "Errore invio");
    }
  };

  const counts = {
    sent: list.filter(n => n.status === "sent").length,
    logged: list.filter(n => n.status === "logged").length,
    failed: list.filter(n => n.status === "failed").length,
  };

  return (
    <div>
      <PageHeader
        eyebrow="Communication"
        title="Notifiche SMS & WhatsApp"
        subtitle={`Invio e storico notifiche al cliente. Provider: ${status.twilio_enabled ? "Twilio attivo" : "Stub (log-only, configura TWILIO_ACCOUNT_SID/AUTH_TOKEN per attivare)"}`}
        actions={
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button className="bg-indaco hover:bg-indaco-dark" data-testid="new-notif-btn">
                <Plus size={16} className="mr-1" />Invia notifica
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-xl">
              <DialogHeader><DialogTitle>Nuova notifica</DialogTitle></DialogHeader>
              <form onSubmit={send} className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label>Canale</Label>
                    <Select value={form.kind} onValueChange={v => setForm({...form, kind: v})}>
                      <SelectTrigger data-testid="notif-kind"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="sms">SMS</SelectItem>
                        <SelectItem value="whatsapp">WhatsApp</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Destinatario (E.164)</Label>
                    <Input required value={form.to} onChange={e => setForm({...form, to: e.target.value})} placeholder="+393331234567" data-testid="notif-to" />
                  </div>
                </div>
                <div>
                  <Label>Template (opzionale)</Label>
                  <Select value={form.template} onValueChange={v => setForm({...form, template: v})}>
                    <SelectTrigger data-testid="notif-template"><SelectValue placeholder="Nessuno — testo libero" /></SelectTrigger>
                    <SelectContent>
                      {status.templates.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                {form.template ? (
                  <div>
                    <Label>Variabili template (JSON)</Label>
                    <Textarea rows={3} value={form.template_vars} onChange={e => setForm({...form, template_vars: e.target.value})} placeholder='{"nome": "Hotel Excelsior", "numero": "CON-2026-00001"}' />
                  </div>
                ) : (
                  <div>
                    <Label>Testo messaggio</Label>
                    <Textarea rows={4} value={form.body} onChange={e => setForm({...form, body: e.target.value})} placeholder="Ciao! La tua consegna è in arrivo..." data-testid="notif-body" />
                  </div>
                )}
                <div className="flex justify-end gap-2">
                  <Button type="button" variant="outline" onClick={() => setOpen(false)}>Annulla</Button>
                  <Button type="submit" className="bg-indaco hover:bg-indaco-dark" data-testid="notif-send-btn">
                    <PaperPlaneTilt size={14} className="mr-1" />Invia
                  </Button>
                </div>
              </form>
            </DialogContent>
          </Dialog>
        }
      />

      {/* KPI */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="kpi-card">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-emerald-100 flex items-center justify-center"><CheckCircle size={20} weight="duotone" className="text-emerald-600" /></div>
            <div><div className="overline">Inviate</div><div className="font-display text-2xl font-bold">{counts.sent}</div></div>
          </div>
        </div>
        <div className="kpi-card">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center"><ChatCircleText size={20} weight="duotone" className="text-slate-600" /></div>
            <div><div className="overline">In log (stub)</div><div className="font-display text-2xl font-bold">{counts.logged}</div></div>
          </div>
        </div>
        <div className="kpi-card">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-red-100 flex items-center justify-center"><XCircle size={20} weight="duotone" className="text-red-600" /></div>
            <div><div className="overline">Fallite</div><div className="font-display text-2xl font-bold text-red-600">{counts.failed}</div></div>
          </div>
        </div>
        <div className="kpi-card">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${status.twilio_enabled ? "bg-emerald-100 text-emerald-600" : "bg-amber-100 text-amber-700"}`}>
              {status.twilio_enabled ? <CheckCircle size={20} weight="duotone" /> : <Warning size={20} weight="duotone" />}
            </div>
            <div><div className="overline">Provider</div><div className="font-display text-sm font-bold">{status.twilio_enabled ? "Twilio LIVE" : "Stub (log)"}</div></div>
          </div>
        </div>
      </div>

      {!status.twilio_enabled && (
        <div className="mb-6 p-4 rounded-md bg-amber-50 border border-amber-200 text-amber-900 text-sm">
          <div className="font-bold mb-1">Twilio non configurato</div>
          Le notifiche sono registrate in log (stub) ma non inviate realmente.
          Configura le env <code className="font-mono bg-amber-100 px-1 rounded">TWILIO_ACCOUNT_SID</code>,
          <code className="font-mono bg-amber-100 px-1 rounded mx-1">TWILIO_AUTH_TOKEN</code>,
          <code className="font-mono bg-amber-100 px-1 rounded">TWILIO_PHONE_NUMBER</code>
          (e opzionalmente <code className="font-mono bg-amber-100 px-1 rounded">TWILIO_WHATSAPP_FROM</code>) sul backend.
        </div>
      )}

      {/* Lista */}
      <div className="space-y-2">
        {list.map(n => {
          const Icon = n.kind === "whatsapp" ? WhatsappLogo : ChatCircleText;
          return (
            <div key={n.id} className="kpi-card flex items-start gap-3" data-testid={`notif-${n.id}`}>
              <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${n.kind === "whatsapp" ? "bg-emerald-100 text-emerald-600" : "bg-sky-100 text-sky-600"}`}>
                <Icon size={20} weight="duotone" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-sm font-bold text-slate-900">{n.to}</span>
                  <span className={`stato-pill capitalize ${STATO_CLS[n.status] || STATO_CLS.logged}`}>{n.status}</span>
                  <span className="text-xs text-slate-400 font-mono">{n.provider}</span>
                </div>
                <div className="text-sm mt-1 text-slate-700">{n.body}</div>
                {n.error && <div className="text-xs text-red-600 mt-1">⚠ {n.error}</div>}
              </div>
              <div className="text-xs text-slate-400 font-mono flex-shrink-0">{new Date(n.created_at).toLocaleString("it-IT")}</div>
            </div>
          );
        })}
        {list.length === 0 && <div className="kpi-card text-center py-12 text-slate-400">Nessuna notifica inviata</div>}
      </div>
    </div>
  );
}
