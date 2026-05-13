import React, { useCallback, useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { toast } from "sonner";
import {
  Database, CloudArrowUp, CloudCheck, Camera, ArrowsClockwise, Trash, FloppyDisk,
  Warning, Bell, EnvelopeSimple, User, Robot, DownloadSimple, UploadSimple,
  CheckCircle, Clock, ShieldWarning, X, Plus, PaperPlaneTilt,
} from "@phosphor-icons/react";

/* -------------------------------------------------------------------------- */
/*  Helpers                                                                    */
/* -------------------------------------------------------------------------- */

const fmtDate = (iso) => {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("it-IT", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return "—"; }
};

const fmtSize = (b) => {
  if (b == null) return "—";
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`;
  return `${(b / 1024 / 1024).toFixed(2)} MB`;
};

const fmtRelative = (iso) => {
  if (!iso) return "mai";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "adesso";
  if (diff < 3600) return `${Math.floor(diff / 60)} min fa`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h fa`;
  return `${Math.floor(diff / 86400)} g fa`;
};

/* -------------------------------------------------------------------------- */
/*  Section card wrapper                                                       */
/* -------------------------------------------------------------------------- */

function SectionCard({ icon: Icon, eyebrow, title, subtitle, accent = "indaco", children, action, "data-testid": tid }) {
  const accents = {
    indaco: "border-indaco/20 bg-indaco/5 text-indaco",
    celeste: "border-celeste/30 bg-celeste/10 text-indaco",
    amber: "border-amber-200 bg-amber-50 text-amber-700",
    red: "border-red-200 bg-red-50 text-red-700",
    emerald: "border-emerald-200 bg-emerald-50 text-emerald-700",
  };
  return (
    <section className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden" data-testid={tid}>
      <header className="px-6 py-4 border-b border-slate-100 flex items-start gap-4">
        <div className={`w-11 h-11 rounded-xl border flex items-center justify-center flex-shrink-0 ${accents[accent]}`}>
          <Icon size={22} weight="duotone" />
        </div>
        <div className="flex-1 min-w-0">
          {eyebrow && <div className="overline text-slate-400">{eyebrow}</div>}
          <h2 className="font-display text-lg font-bold text-slate-900 leading-tight">{title}</h2>
          {subtitle && <p className="text-sm text-slate-500 mt-0.5">{subtitle}</p>}
        </div>
        {action && <div className="flex-shrink-0">{action}</div>}
      </header>
      <div className="p-6 space-y-4">{children}</div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/*  Main page                                                                  */
/* -------------------------------------------------------------------------- */

export default function BackupDati() {
  return (
    <div className="space-y-6 max-w-5xl mx-auto" data-testid="backup-dati-page">
      <PageHeader
        eyebrow="Disaster recovery"
        title="Backup & Dati"
        subtitle="Snapshot automatici su cloud, backup manuali in JSON, notifiche email per gli alert e zona pericolosa per il reset operativo."
      />

      <StatusStrip />

      <CloudSnapshotsCard />

      <NotificationCard />

      <ManualBackupCard />

      <DangerZoneCard />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Status strip — overview KPIs                                               */
/* -------------------------------------------------------------------------- */

function StatusStrip() {
  const [stats, setStats] = useState({ count: 0, latest: null, retention: 7, size: 0 });

  useEffect(() => {
    api.get("/company/backup/cloud/list").then(({ data }) => {
      const snaps = data.snapshots || [];
      setStats({
        count: snaps.length,
        latest: snaps[0]?.created_at || null,
        retention: data.retention_days || 7,
        size: snaps.reduce((acc, s) => acc + (s.size_bytes || 0), 0),
      });
    }).catch(() => {});
  }, []);

  const cards = [
    { label: "Snapshot attivi", value: stats.count, sub: `max ${stats.retention}`, icon: Database, accent: "text-indaco" },
    { label: "Ultimo backup", value: fmtRelative(stats.latest), sub: fmtDate(stats.latest), icon: Clock, accent: "text-emerald-600" },
    { label: "Spazio occupato", value: fmtSize(stats.size), sub: "in cloud", icon: CloudCheck, accent: "text-celeste" },
    { label: "Scheduler", value: "03:00 UTC", sub: "giornaliero", icon: ArrowsClockwise, accent: "text-amber-600" },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3" data-testid="backup-status-strip">
      {cards.map((c) => (
        <div key={c.label} className="bg-white rounded-xl border border-slate-200 p-4 hover:shadow-sm transition-shadow">
          <div className="flex items-center gap-2 mb-2">
            <c.icon size={16} weight="duotone" className={c.accent} />
            <span className="overline text-slate-400">{c.label}</span>
          </div>
          <div className="font-display text-2xl font-bold text-slate-900 leading-none">{c.value}</div>
          <div className="text-xs text-slate-500 mt-1 font-mono truncate">{c.sub}</div>
        </div>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Card: Cloud snapshots                                                      */
/* -------------------------------------------------------------------------- */

function CloudSnapshotsCard() {
  const [snapshots, setSnapshots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [retention, setRetention] = useState(7);
  const [restoreState, setRestoreState] = useState({ open: false, id: null, mode: "merge", confirm: "", running: false });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/company/backup/cloud/list");
      setSnapshots(data.snapshots || []);
      setRetention(data.retention_days || 7);
    } catch (e) {
      toast.error("Errore caricamento snapshot");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const createNow = async () => {
    setCreating(true);
    try {
      const { data } = await api.post("/company/backup/cloud");
      toast.success(`Snapshot creato · ${fmtSize(data.snapshot.size_bytes)} · ${data.snapshot.total_records} record`);
      if (data.pruned > 0) toast.info(`${data.pruned} snapshot più vecchi rimossi per retention`);
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore creazione snapshot");
    } finally { setCreating(false); }
  };

  const askRestore = (id) => setRestoreState({ open: true, id, mode: "merge", confirm: "", running: false });

  const doRestore = async () => {
    const { id, mode, confirm } = restoreState;
    if (confirm !== "RESTORE" || !id) return;
    setRestoreState((s) => ({ ...s, running: true }));
    try {
      const { data } = await api.post(`/company/backup/cloud/${id}/restore`, { confirm: "RESTORE", mode });
      toast.success(`${data.total_inserted + data.total_updated} record ripristinati`);
      setRestoreState({ open: false, id: null, mode: "merge", confirm: "", running: false });
      setTimeout(() => window.location.reload(), 1200);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore ripristino");
      setRestoreState((s) => ({ ...s, running: false }));
    }
  };

  const deleteSnap = async (id) => {
    if (!window.confirm("Eliminare definitivamente questo snapshot?")) return;
    try {
      await api.delete(`/company/backup/cloud/${id}`);
      toast.success("Snapshot eliminato");
      await load();
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  return (
    <SectionCard
      data-testid="cloud-snapshots-card"
      icon={CloudArrowUp}
      eyebrow="Cloud · automatico"
      title="Snapshot su archiviazione cloud"
      subtitle={`Backup giornaliero alle 03:00 UTC · retention ${retention} snapshot · ripristino con 1 click`}
      accent="indaco"
      action={
        <Button onClick={createNow} disabled={creating} className="bg-indaco hover:bg-indaco-dark" data-testid="cloud-backup-create-btn">
          <Camera size={16} weight="duotone" className="mr-1.5" />
          {creating ? "Creazione…" : "Crea snapshot"}
        </Button>
      }
    >
      <div className="rounded-xl border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="text-left px-4 py-2.5 font-medium">Data</th>
              <th className="text-left px-4 py-2.5 font-medium">Origine</th>
              <th className="text-right px-4 py-2.5 font-medium">Record</th>
              <th className="text-right px-4 py-2.5 font-medium">Dimensione</th>
              <th className="text-right px-4 py-2.5 font-medium">Azioni</th>
            </tr>
          </thead>
          <tbody data-testid="cloud-backup-list">
            {loading ? (
              <tr><td colSpan={5} className="text-center py-8 text-slate-400 font-mono text-xs">Caricamento…</td></tr>
            ) : snapshots.length === 0 ? (
              <tr>
                <td colSpan={5} className="text-center py-10">
                  <CloudCheck size={36} weight="duotone" className="mx-auto text-slate-300 mb-2" />
                  <p className="text-sm text-slate-500">Nessuno snapshot ancora.</p>
                  <p className="text-xs text-slate-400 mt-1">Creane uno manualmente o attendi il run automatico delle 03:00 UTC.</p>
                </td>
              </tr>
            ) : (
              snapshots.map((s) => (
                <tr key={s.id} className="border-t border-slate-100 hover:bg-slate-50/60 transition-colors" data-testid={`cloud-backup-row-${s.id}`}>
                  <td className="px-4 py-3">
                    <div className="font-mono text-xs text-slate-900">{fmtDate(s.created_at)}</div>
                    <div className="text-[11px] text-slate-400">{fmtRelative(s.created_at)}</div>
                  </td>
                  <td className="px-4 py-3">
                    {s.source === "auto" ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-indaco/10 text-indaco">
                        <Robot size={12} weight="duotone" /> auto
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-100 text-amber-700">
                        <User size={12} weight="duotone" /> manuale
                      </span>
                    )}
                    {s.source !== "auto" && s.created_by && (
                      <span className="ml-2 text-[11px] text-slate-400 font-mono">{s.created_by}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-slate-700">{s.total_records}</td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-slate-700">{fmtSize(s.size_bytes)}</td>
                  <td className="px-4 py-3 text-right space-x-1.5 whitespace-nowrap">
                    <button
                      type="button"
                      onClick={() => askRestore(s.id)}
                      className="inline-flex items-center gap-1 px-2.5 py-1 text-xs bg-emerald-600 hover:bg-emerald-700 text-white rounded-md transition-colors"
                      data-testid={`cloud-backup-restore-btn-${s.id}`}>
                      <ArrowsClockwise size={12} weight="bold" /> Ripristina
                    </button>
                    <button
                      type="button"
                      onClick={() => deleteSnap(s.id)}
                      className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-white border border-red-300 text-red-600 hover:bg-red-50 rounded-md transition-colors"
                      data-testid={`cloud-backup-delete-btn-${s.id}`}>
                      <Trash size={12} weight="bold" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {restoreState.open && (
        <div className="rounded-xl border-2 border-emerald-300 bg-emerald-50/60 p-4 space-y-3" data-testid="cloud-backup-restore-dialog">
          <div className="flex items-center gap-2 text-emerald-800 font-display font-bold">
            <ArrowsClockwise size={18} weight="duotone" /> Ripristino snapshot
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <button type="button" onClick={() => setRestoreState((s) => ({ ...s, mode: "merge" }))}
              className={`text-left rounded-lg border-2 p-3 transition-all ${restoreState.mode === "merge" ? "border-indaco bg-white shadow-sm" : "border-slate-200 bg-white/70 hover:bg-white"}`}
              data-testid="cloud-restore-mode-merge">
              <div className="font-bold text-sm text-slate-900 mb-1">Merge (consigliato)</div>
              <div className="text-xs text-slate-500">Sovrascrive i record per ID. I nuovi record non vengono toccati.</div>
            </button>
            <button type="button" onClick={() => setRestoreState((s) => ({ ...s, mode: "replace" }))}
              className={`text-left rounded-lg border-2 p-3 transition-all ${restoreState.mode === "replace" ? "border-red-500 bg-white shadow-sm" : "border-slate-200 bg-white/70 hover:bg-white"}`}
              data-testid="cloud-restore-mode-replace">
              <div className="font-bold text-sm text-slate-900 mb-1">Replace</div>
              <div className="text-xs text-slate-500">Cancella TUTTI i dati operativi del tenant, poi importa.</div>
            </button>
          </div>
          <div>
            <Label className="text-emerald-800">Digita <code className="bg-white px-1.5 py-0.5 rounded border border-emerald-300 font-mono text-xs">RESTORE</code> per confermare</Label>
            <Input
              autoFocus
              value={restoreState.confirm}
              onChange={(e) => setRestoreState((s) => ({ ...s, confirm: e.target.value }))}
              placeholder="RESTORE"
              className="mt-1 border-emerald-300 font-mono"
              data-testid="cloud-restore-confirm-input"
            />
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setRestoreState({ open: false, id: null, mode: "merge", confirm: "", running: false })}>
              Annulla
            </Button>
            <Button
              onClick={doRestore}
              disabled={restoreState.confirm !== "RESTORE" || restoreState.running}
              className="bg-emerald-600 hover:bg-emerald-700"
              data-testid="cloud-restore-execute-btn">
              {restoreState.running ? "Ripristino in corso…" : "Conferma ripristino"}
            </Button>
          </div>
        </div>
      )}
    </SectionCard>
  );
}

/* -------------------------------------------------------------------------- */
/*  Card: Notifiche email                                                      */
/* -------------------------------------------------------------------------- */

function NotificationCard() {
  const [recipients, setRecipients] = useState([]);
  const [includeAdmin, setIncludeAdmin] = useState(true);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/company/notifications");
      setRecipients(data.recipients || []);
      setIncludeAdmin(data.include_admin !== false);
    } catch (e) { toast.error("Errore caricamento notifiche"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const isValidEmail = (e) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test((e || "").trim());

  const addEmail = () => {
    const e = draft.trim().toLowerCase();
    if (!e) return;
    if (!isValidEmail(e)) { toast.error("Email non valida"); return; }
    if (recipients.includes(e)) { toast.info("Email già presente"); setDraft(""); return; }
    if (recipients.length >= 20) { toast.error("Massimo 20 destinatari"); return; }
    setRecipients([...recipients, e]);
    setDraft("");
  };

  const removeEmail = (e) => setRecipients(recipients.filter((x) => x !== e));

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.put("/company/notifications", { recipients, include_admin: includeAdmin });
      setRecipients(data.recipients || []);
      setIncludeAdmin(data.include_admin !== false);
      toast.success("Notifiche salvate");
    } catch (e) { toast.error(e.response?.data?.detail || "Errore salvataggio"); }
    finally { setSaving(false); }
  };

  const sendTest = async () => {
    setTesting(true);
    try {
      const { data } = await api.post("/company/notifications/test");
      const ok = data.sent.filter((s) => s.status === "sent").length;
      const stub = data.sent.filter((s) => s.status === "logged").length;
      const failed = data.sent.filter((s) => s.status === "failed").length;
      if (failed > 0) toast.error(`${failed} email fallite`);
      else if (stub > 0) toast.info(`Email registrate nel log (SMTP non configurato): ${stub}`);
      else toast.success(`${ok} email di test inviate`);
    } catch (e) { toast.error(e.response?.data?.detail || "Errore invio test"); }
    finally { setTesting(false); }
  };

  return (
    <SectionCard
      data-testid="notification-settings"
      icon={Bell}
      eyebrow="Avvisi · email"
      title="Notifiche email"
      subtitle="Chi viene avvisato se un backup automatico fallisce."
      accent="celeste"
    >
      <label className="flex items-start gap-3 p-3 rounded-lg bg-slate-50 border border-slate-200 cursor-pointer hover:bg-slate-100/60 transition-colors">
        <input
          type="checkbox"
          checked={includeAdmin}
          onChange={(e) => setIncludeAdmin(e.target.checked)}
          className="mt-1 accent-indaco"
          data-testid="notif-include-admin"
        />
        <span className="flex-1">
          <span className="font-medium text-slate-900 text-sm">Includi tutti gli amministratori del tenant</span>
          <span className="block text-xs text-slate-500 mt-0.5">
            Invia anche agli utenti con ruolo <code className="bg-white px-1 py-0.5 rounded border border-slate-200 font-mono">admin</code> attivi.
          </span>
        </span>
      </label>

      <div>
        <Label className="flex items-center gap-1.5">
          <EnvelopeSimple size={14} weight="duotone" /> Destinatari aggiuntivi
          <span className="text-slate-400 font-normal">· max 20</span>
        </Label>
        <div className="flex gap-2 mt-1.5">
          <Input
            type="email"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addEmail(); } }}
            placeholder="es. it@tuaazienda.it"
            data-testid="notif-email-input"
          />
          <Button onClick={addEmail} variant="outline" data-testid="notif-add-btn">
            <Plus size={14} weight="bold" className="mr-1" /> Aggiungi
          </Button>
        </div>

        {loading ? (
          <p className="mt-3 text-xs text-slate-400 font-mono">Caricamento…</p>
        ) : recipients.length === 0 ? (
          <p className="mt-3 text-xs text-slate-400 italic">Nessun destinatario aggiuntivo. Aggiungi un'email qui sopra.</p>
        ) : (
          <ul className="mt-3 flex flex-wrap gap-2" data-testid="notif-recipients-list">
            {recipients.map((e) => (
              <li key={e}
                className="inline-flex items-center gap-2 bg-celeste/10 text-indaco border border-celeste/30 rounded-full pl-3 pr-1 py-1 text-xs font-mono group hover:bg-celeste/15 transition-colors"
                data-testid={`notif-chip-${e}`}>
                <EnvelopeSimple size={12} weight="duotone" />
                {e}
                <button
                  type="button"
                  onClick={() => removeEmail(e)}
                  className="w-5 h-5 rounded-full hover:bg-red-500 hover:text-white text-indaco/60 flex items-center justify-center transition-colors"
                  aria-label={`Rimuovi ${e}`}
                  data-testid={`notif-remove-${e}`}>
                  <X size={11} weight="bold" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex flex-wrap gap-2 pt-3 border-t border-slate-100">
        <Button onClick={save} disabled={saving} className="bg-indaco hover:bg-indaco-dark" data-testid="notif-save-btn">
          <FloppyDisk size={14} weight="duotone" className="mr-1.5" />
          {saving ? "Salvataggio…" : "Salva"}
        </Button>
        <Button onClick={sendTest} variant="outline" disabled={testing || (recipients.length === 0 && !includeAdmin)} data-testid="notif-test-btn">
          <PaperPlaneTilt size={14} weight="duotone" className="mr-1.5" />
          {testing ? "Invio…" : "Invia email di test"}
        </Button>
      </div>
    </SectionCard>
  );
}

/* -------------------------------------------------------------------------- */
/*  Card: Manual backup (export/import JSON)                                   */
/* -------------------------------------------------------------------------- */

function ManualBackupCard() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [mode, setMode] = useState("merge");
  const [confirmText, setConfirmText] = useState("");
  const [restoring, setRestoring] = useState(false);
  const [downloading, setDownloading] = useState(false);

  const downloadBackup = async () => {
    setDownloading(true);
    try {
      const res = await api.get("/company/export-operativo", { responseType: "blob" });
      const disp = res.headers["content-disposition"] || "";
      const match = disp.match(/filename="?([^";]+)"?/);
      const filename = match ? match[1] : `backup-${new Date().toISOString().slice(0, 10)}.json`;
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = filename; a.click();
      URL.revokeObjectURL(url);
      toast.success("Backup JSON scaricato");
    } catch (e) {
      toast.error("Errore download backup: " + (e.response?.data?.detail || e.message));
    } finally { setDownloading(false); }
  };

  const onFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f); setPreview(null);
    try {
      const text = await f.text();
      const data = JSON.parse(text);
      const counts = Object.fromEntries(
        Object.entries(data.collections || {}).map(([k, v]) => [k, Array.isArray(v) ? v.length : 0])
      );
      setPreview({
        tenant_id: data.tenant_id, exported_at: data.exported_at,
        total: Object.values(counts).reduce((a, b) => a + b, 0), counts,
      });
    } catch (e2) { toast.error("File non valido: " + e2.message); setFile(null); }
  };

  const doRestore = async () => {
    if (!file || confirmText !== "RESTORE") return;
    setRestoring(true);
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      const { data: res } = await api.post("/company/restore-operativo", { confirm: "RESTORE", mode, data });
      toast.success(`${res.total_inserted + res.total_updated} record ripristinati`);
      setTimeout(() => window.location.reload(), 1200);
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    finally { setRestoring(false); }
  };

  return (
    <SectionCard
      data-testid="manual-backup-card"
      icon={Database}
      eyebrow="Manuale · JSON"
      title="Backup & ripristino su file"
      subtitle="Esporta uno snapshot in formato JSON locale, oppure ripristina un backup da file."
      accent="amber"
    >
      {/* Export */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="rounded-xl border border-slate-200 p-4 hover:border-amber-300 transition-colors">
          <div className="flex items-center gap-2 mb-2">
            <DownloadSimple size={18} weight="duotone" className="text-amber-700" />
            <h3 className="font-display font-bold text-sm">Scarica backup completo</h3>
          </div>
          <p className="text-xs text-slate-500 mb-3">
            Un singolo file <code className="font-mono bg-slate-100 px-1 rounded">.json</code> con tutto: clienti, DDT, fatture, fornitori, costi, catalogo, anagrafica.
          </p>
          <Button onClick={downloadBackup} disabled={downloading} className="bg-amber-600 hover:bg-amber-700 text-white" data-testid="download-backup-btn">
            <DownloadSimple size={14} weight="bold" className="mr-1.5" />
            {downloading ? "Esportazione…" : "Scarica JSON"}
          </Button>
        </div>

        <div className="rounded-xl border border-slate-200 p-4 hover:border-amber-300 transition-colors">
          <div className="flex items-center gap-2 mb-2">
            <UploadSimple size={18} weight="duotone" className="text-amber-700" />
            <h3 className="font-display font-bold text-sm">Carica backup da file</h3>
          </div>
          <p className="text-xs text-slate-500 mb-3">
            Seleziona un file JSON precedentemente esportato per ripristinare i dati.
          </p>
          <input
            type="file"
            accept="application/json,.json"
            onChange={onFile}
            data-testid="restore-file-input"
            className="block w-full text-xs border border-slate-200 rounded-md file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:bg-amber-600 file:text-white file:cursor-pointer file:text-xs hover:file:bg-amber-700"
          />
        </div>
      </div>

      {preview && (
        <div className="rounded-xl border-2 border-amber-300 bg-amber-50/40 p-4 space-y-3" data-testid="restore-preview">
          <div className="grid grid-cols-3 gap-3 text-xs">
            <div>
              <div className="overline text-slate-400">Tenant nel backup</div>
              <div className="font-mono text-slate-900 truncate" title={preview.tenant_id}>{preview.tenant_id || "—"}</div>
            </div>
            <div>
              <div className="overline text-slate-400">Esportato il</div>
              <div className="font-mono text-slate-900">{fmtDate(preview.exported_at)}</div>
            </div>
            <div>
              <div className="overline text-slate-400">Totale record</div>
              <div className="font-display text-lg font-bold text-amber-700">{preview.total}</div>
            </div>
          </div>

          <div>
            <div className="overline text-slate-500 mb-2">Modalità ripristino</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <button type="button" onClick={() => setMode("merge")}
                className={`text-left rounded-lg border-2 p-3 transition-all ${mode === "merge" ? "border-indaco bg-white shadow-sm" : "border-slate-200 bg-white/70"}`}
                data-testid="restore-mode-merge">
                <div className="font-bold text-sm text-slate-900">Merge</div>
                <div className="text-xs text-slate-500 mt-0.5">Aggiorna per ID, conserva i nuovi.</div>
              </button>
              <button type="button" onClick={() => setMode("replace")}
                className={`text-left rounded-lg border-2 p-3 transition-all ${mode === "replace" ? "border-red-500 bg-white shadow-sm" : "border-slate-200 bg-white/70"}`}
                data-testid="restore-mode-replace">
                <div className="font-bold text-sm text-slate-900">Replace</div>
                <div className="text-xs text-slate-500 mt-0.5">Wipe completo + import.</div>
              </button>
            </div>
          </div>

          <div>
            <Label>Digita <code className="bg-white px-1.5 py-0.5 rounded border border-amber-300 font-mono text-xs">RESTORE</code> per confermare</Label>
            <Input
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="RESTORE"
              className="mt-1 border-amber-300 font-mono"
              data-testid="restore-confirm-input"
            />
          </div>

          <Button onClick={doRestore} disabled={confirmText !== "RESTORE" || restoring} className="bg-amber-600 hover:bg-amber-700 text-white" data-testid="restore-execute-btn">
            <ArrowsClockwise size={14} weight="bold" className="mr-1.5" />
            {restoring ? "Ripristino…" : "Esegui ripristino"}
          </Button>
        </div>
      )}
    </SectionCard>
  );
}

/* -------------------------------------------------------------------------- */
/*  Card: Danger Zone                                                          */
/* -------------------------------------------------------------------------- */

function DangerZoneCard() {
  const [open, setOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [resetCounters, setResetCounters] = useState(true);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const doReset = async () => {
    if (confirmText !== "RESET") return;
    setLoading(true);
    try {
      const { data } = await api.post("/company/reset-operativo", { confirm: "RESET", reset_counters: resetCounters });
      setResult(data);
      toast.success(`${data.total_deleted} record cancellati`);
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    finally { setLoading(false); }
  };

  return (
    <SectionCard
      data-testid="danger-zone"
      icon={ShieldWarning}
      eyebrow="Pericoloso · irreversibile"
      title="Zona pericolosa"
      subtitle="Reset operativo del tenant. Operazione permanente — fai sempre un backup prima."
      accent="red"
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="rounded-lg border border-red-200 bg-red-50/40 p-3">
          <div className="flex items-center gap-1.5 text-red-700 font-bold text-xs mb-2 uppercase tracking-wide">
            <Warning size={14} weight="fill" /> Verrà cancellato
          </div>
          <ul className="space-y-0.5 text-xs text-slate-700">
            <li>· Clienti, Fornitori</li>
            <li>· DDT, Fatture, Sospesi, Ordinativi</li>
            <li>· Offerte, Contratti</li>
            <li>· Costi, Dipendenti, Automezzi</li>
            <li>· Audit log, Email log, Sessioni portale</li>
          </ul>
        </div>
        <div className="rounded-lg border border-emerald-200 bg-emerald-50/40 p-3">
          <div className="flex items-center gap-1.5 text-emerald-700 font-bold text-xs mb-2 uppercase tracking-wide">
            <CheckCircle size={14} weight="fill" /> NON sarà toccato
          </div>
          <ul className="space-y-0.5 text-xs text-slate-700">
            <li>· Articoli (catalogo)</li>
            <li>· Listini & Prezzi</li>
            <li>· Anagrafica azienda + Logo</li>
            <li>· Branding</li>
            <li>· Utenti & Login</li>
          </ul>
        </div>
      </div>

      {!result && !open && (
        <Button onClick={() => setOpen(true)} variant="outline" className="border-red-300 text-red-600 hover:bg-red-50" data-testid="open-reset-dialog">
          <Warning size={14} weight="duotone" className="mr-1.5" />
          Apri procedura di reset
        </Button>
      )}

      {open && !result && (
        <div className="rounded-xl border-2 border-red-300 bg-red-50/60 p-4 space-y-3">
          <Label className="text-red-700 font-bold flex items-center gap-1.5">
            <ShieldWarning size={16} weight="duotone" /> Digita <code className="bg-white px-1.5 py-0.5 rounded border border-red-300 font-mono text-xs">RESET</code> per confermare
          </Label>
          <Input
            autoFocus
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            placeholder="RESET"
            className="border-red-300 font-mono"
            data-testid="reset-confirm-input"
          />
          <label className="flex items-center gap-2 text-xs text-slate-700">
            <input type="checkbox" checked={resetCounters} onChange={(e) => setResetCounters(e.target.checked)} className="accent-red-600" data-testid="reset-counters-checkbox" />
            Resetta anche i contatori di numerazione (DDT, FT, ORD ripartono da 1)
          </label>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => { setOpen(false); setConfirmText(""); }}>Annulla</Button>
            <Button onClick={doReset} disabled={confirmText !== "RESET" || loading} className="bg-red-600 hover:bg-red-700 text-white" data-testid="reset-execute-btn">
              <Trash size={14} weight="duotone" className="mr-1.5" />
              {loading ? "Cancellazione…" : "Cancella tutto"}
            </Button>
          </div>
        </div>
      )}

      {result && (
        <div className="rounded-xl border-2 border-emerald-300 bg-emerald-50/60 p-4" data-testid="reset-result">
          <div className="flex items-center gap-2 font-display font-bold text-emerald-700 mb-1">
            <CheckCircle size={18} weight="duotone" /> Operazione completata
          </div>
          <p className="text-sm text-slate-700">{result.message}</p>
          <Button onClick={() => window.location.reload()} className="mt-3 bg-emerald-600 hover:bg-emerald-700">
            Ricarica pagina
          </Button>
        </div>
      )}
    </SectionCard>
  );
}
