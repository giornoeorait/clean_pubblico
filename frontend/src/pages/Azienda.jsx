import React, { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { toast } from "sonner";
import { Buildings, FloppyDisk, UploadSimple, Trash, ImageSquare, CheckCircle, Warning, Sparkle } from "@phosphor-icons/react";

const BACKEND = process.env.REACT_APP_BACKEND_URL;

const FIELDS = [
  { k: "nome",             label: "Nome azienda",            required: true,  placeholder: "CleanTec Demo" },
  { k: "ragione_sociale",  label: "Ragione sociale",         required: true,  placeholder: "CleanTec Demo Srl" },
  { k: "partita_iva",      label: "Partita IVA",             required: true,  placeholder: "IT01234567890" },
  { k: "codice_fiscale",   label: "Codice fiscale",          required: false, placeholder: "01234567890" },
  { k: "indirizzo",        label: "Indirizzo completo",      required: true,  placeholder: "Via Roma 123, 20100 Milano (MI)" },
  { k: "iban",             label: "IBAN",                    required: false, placeholder: "IT60 X 05428 11101 00000 0123456" },
  { k: "email",            label: "Email",                   required: true,  placeholder: "info@tuaazienda.it" },
  { k: "pec",              label: "PEC",                     required: false, placeholder: "azienda@pec.it" },
  { k: "codice_sdi",       label: "Codice destinatario SDI", required: false, placeholder: "0000000 oppure ABC1234" },
  { k: "telefono",         label: "Telefono",                required: true,  placeholder: "+39 02 1234567" },
  { k: "sito_web",         label: "Sito internet",           required: false, placeholder: "https://tuaazienda.it" },
];

export default function Azienda() {
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [imgVersion, setImgVersion] = useState(0);
  const location = useLocation();
  const navigate = useNavigate();
  const fileRef = useRef(null);
  const firstRun = new URLSearchParams(location.search).get("first") === "1";

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/company");
      setForm(data);
    } catch (e) {
      toast.error("Errore caricamento anagrafica");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (!form) return <div className="text-slate-400 font-mono text-sm">Caricamento…</div>;

  const update = (k, v) => setForm({ ...form, [k]: v });

  const missingRequired = FIELDS.filter(f => f.required && !(form[f.k] || "").trim()).map(f => f.label);
  const isComplete = missingRequired.length === 0;

  const save = async () => {
    if (!isComplete) {
      toast.error(`Campi obbligatori mancanti: ${missingRequired.join(", ")}`);
      return;
    }
    setSaving(true);
    try {
      const payload = Object.fromEntries(FIELDS.map(f => [f.k, form[f.k] || ""]));
      const { data } = await api.put("/company", payload);
      setForm(data);
      toast.success("Anagrafica salvata");
      if (firstRun) {
        setTimeout(() => navigate("/dashboard"), 500);
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore salvataggio");
    } finally {
      setSaving(false);
    }
  };

  const uploadLogo = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const { data } = await api.post("/company/logo", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(`Logo caricato (${(data.size / 1024).toFixed(1)} KB · ${data.width}×${data.height})`);
      await load();
      setImgVersion(v => v + 1);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Upload fallito");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const deleteLogo = async () => {
    if (!window.confirm("Rimuovere il logo?")) return;
    try {
      await api.delete("/company/logo");
      toast.success("Logo rimosso");
      await load();
      setImgVersion(v => v + 1);
    } catch (e) {
      toast.error("Errore");
    }
  };

  return (
    <div className="space-y-6" data-testid="azienda-page">
      {firstRun && !form.setup_complete && (
        <div className="rounded-lg border border-indaco/30 bg-gradient-to-br from-indaco/5 to-celeste/5 p-5" data-testid="first-run-banner">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-lg bg-indaco flex items-center justify-center flex-shrink-0">
              <Sparkle size={22} weight="fill" className="text-white" />
            </div>
            <div>
              <div className="font-display font-bold text-lg text-indaco">Benvenuto in CleanTec!</div>
              <p className="text-sm text-slate-700 mt-1 max-w-2xl">
                Prima di iniziare, completa l'anagrafica della tua azienda. Questi dati saranno usati come intestazione di tutti i documenti generati (DDT, fatture, offerte, contratti).
              </p>
            </div>
          </div>
        </div>
      )}

      <PageHeader
        eyebrow="Setup iniziale"
        title="Anagrafica azienda"
        subtitle="I dati inseriti qui appariranno come intestazione su tutti i PDF: DDT, fatture, offerte commerciali e contratti."
        actions={
          <Button onClick={save} disabled={saving || !isComplete} className="bg-indaco hover:bg-indaco-dark" data-testid="azienda-save-btn">
            <FloppyDisk size={16} className="mr-2" />{saving ? "Salvataggio…" : isComplete ? "Salva anagrafica" : `Compila ${missingRequired.length} campi`}
          </Button>
        }
      />

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Form */}
        <div className="xl:col-span-2 kpi-card">
          <h3 className="font-display text-lg font-bold mb-4 flex items-center gap-2">
            <Buildings size={20} className="text-indaco" />Dati aziendali
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {FIELDS.map(f => {
              const val = form[f.k] || "";
              const missing = f.required && !val.trim();
              return (
                <div key={f.k}>
                  <Label>
                    {f.label}
                    {f.required && <span className="text-red-500 ml-0.5">*</span>}
                  </Label>
                  <Input
                    value={val}
                    onChange={e => update(f.k, e.target.value)}
                    placeholder={f.placeholder}
                    data-testid={`azienda-${f.k}`}
                    className={missing ? "border-amber-300" : ""}
                  />
                </div>
              );
            })}
          </div>
          {!isComplete && (
            <div className="mt-4 flex items-center gap-2 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
              <Warning size={16} weight="fill" />
              <span>Campi obbligatori ancora da compilare: <b>{missingRequired.join(", ")}</b></span>
            </div>
          )}
        </div>

        {/* Logo + status */}
        <div className="space-y-4">
          <div className="kpi-card" data-testid="azienda-logo-card">
            <h3 className="font-display text-lg font-bold mb-3 flex items-center gap-2">
              <ImageSquare size={20} className="text-indaco" />Logo azienda
            </h3>
            <p className="text-xs text-slate-500 mb-4">Apparirà in alto a sinistra su tutti i PDF (DDT, fatture, offerte). Max 4 MB, auto-resize 512×512, convertito in WebP.</p>
            <div className="w-full aspect-square rounded-lg border-2 border-dashed border-slate-200 flex items-center justify-center mb-3 bg-slate-50">
              {form.logo_url ? (
                <img
                  src={`${BACKEND}${form.logo_url}?v=${imgVersion}`}
                  alt="Logo"
                  className="max-w-full max-h-full object-contain p-4"
                />
              ) : (
                <div className="text-slate-300 text-center">
                  <ImageSquare size={48} className="mx-auto" />
                  <div className="text-xs mt-2 font-mono">Nessun logo</div>
                </div>
              )}
            </div>
            <input type="file" ref={fileRef} accept="image/png,image/jpeg,image/webp,image/svg+xml" onChange={uploadLogo} className="hidden" id="company-logo-input" data-testid="azienda-logo-input" />
            <div className="flex gap-2">
              <label htmlFor="company-logo-input" className="flex-1">
                <Button asChild type="button" variant="outline" disabled={uploading} className="w-full cursor-pointer" data-testid="azienda-upload-logo-btn">
                  <span><UploadSimple size={14} className="mr-1" />{uploading ? "Caricamento…" : (form.logo_url ? "Sostituisci" : "Carica logo")}</span>
                </Button>
              </label>
              {form.logo_url && (
                <Button type="button" variant="outline" size="icon" onClick={deleteLogo} className="text-red-500" data-testid="azienda-delete-logo-btn">
                  <Trash size={14} />
                </Button>
              )}
            </div>
          </div>

          <div className="kpi-card">
            <div className="overline mb-2">Stato anagrafica</div>
            {isComplete ? (
              <div className="flex items-center gap-2 text-emerald-600" data-testid="azienda-complete">
                <CheckCircle size={20} weight="fill" />
                <span className="font-semibold">Configurazione completa</span>
              </div>
            ) : (
              <div className="flex items-center gap-2 text-amber-600" data-testid="azienda-incomplete">
                <Warning size={20} weight="fill" />
                <span className="font-semibold">Incompleta ({FIELDS.filter(f=>f.required).length - missingRequired.length}/{FIELDS.filter(f=>f.required).length} obbligatori)</span>
              </div>
            )}
            <div className="text-xs text-slate-500 mt-3 font-mono">
              I PDF generati prima del completamento avranno l'intestazione parzialmente vuota.
            </div>
          </div>
        </div>
      </div>

      {/* DANGER ZONE */}
      <DangerZone />
      <CloudBackups />
    </div>
  );
}

function DangerZone() {
  const [open, setOpen] = React.useState(false);
  const [confirmText, setConfirmText] = React.useState("");
  const [resetCounters, setResetCounters] = React.useState(true);
  const [loading, setLoading] = React.useState(false);
  const [result, setResult] = React.useState(null);
  const [downloadedBackup, setDownloadedBackup] = React.useState(false);
  const [backingUp, setBackingUp] = React.useState(false);

  const downloadBackup = async () => {
    setBackingUp(true);
    try {
      const res = await api.get("/company/export-operativo", { responseType: "blob" });
      // Estrae nome file dall'header
      const disp = res.headers["content-disposition"] || "";
      const match = disp.match(/filename="?([^";]+)"?/);
      const filename = match ? match[1] : `backup-${new Date().toISOString().slice(0,10)}.json`;
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = filename; a.click();
      URL.revokeObjectURL(url);
      setDownloadedBackup(true);
      toast.success("Backup scaricato — conservalo in un posto sicuro");
    } catch (e) {
      toast.error("Errore download backup: " + (e.response?.data?.detail || e.message));
    } finally { setBackingUp(false); }
  };

  const doReset = async () => {
    if (confirmText !== "RESET") return;
    setLoading(true);
    try {
      const { data } = await api.post("/company/reset-operativo", { confirm: "RESET", reset_counters: resetCounters });
      setResult(data);
      toast.success(`${data.total_deleted} record cancellati`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore");
    } finally { setLoading(false); }
  };

  return (
    <div className="mt-12 max-w-4xl mx-auto" data-testid="danger-zone">
      <details className="rounded-lg border-2 border-red-200 bg-red-50/30 overflow-hidden">
        <summary className="px-5 py-3 cursor-pointer font-display font-bold text-red-700 hover:bg-red-100/40 select-none">
          ⚠️ Zona pericolosa — Reset dati operativi
        </summary>
        <div className="p-5 border-t border-red-200 bg-white space-y-4">
          <p className="text-sm text-slate-700">
            Questa operazione <b>cancella in modo irreversibile</b> tutti i dati operativi del tuo tenant:
          </p>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <p className="font-bold text-red-700 mb-1">❌ Verrà cancellato:</p>
              <ul className="space-y-0.5 text-slate-600">
                <li>• Clienti</li>
                <li>• DDT, Fatture, Sospesi</li>
                <li>• Offerte, Contratti, Ordinativi</li>
                <li>• Fornitori, DDT fornitore, Fatture fornitore</li>
                <li>• Costi, Dipendenti, Automezzi</li>
                <li>• Sessioni portale, Audit log, Email log</li>
              </ul>
            </div>
            <div>
              <p className="font-bold text-emerald-700 mb-1">✅ NON sarà toccato:</p>
              <ul className="space-y-0.5 text-slate-600">
                <li>• Articoli (catalogo)</li>
                <li>• Listini & Prezzi</li>
                <li>• Anagrafica Azienda (questa)</li>
                <li>• Branding & Logo</li>
                <li>• Utenti & Login</li>
                <li>• Termini di pagamento</li>
              </ul>
            </div>
          </div>

          {!result && !open && (
            <button
              type="button"
              onClick={() => setOpen(true)}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-md text-sm font-medium"
              data-testid="open-reset-dialog">
              Apri procedura di reset
            </button>
          )}

          {open && !result && (
            <div className="border-2 border-red-300 rounded-lg p-4 bg-red-50 space-y-3">
              <div className="bg-amber-50 border border-amber-300 rounded-md p-3 flex items-start gap-2 text-sm">
                <span className="text-2xl leading-none">💾</span>
                <div className="flex-1">
                  <p className="font-bold text-amber-800 mb-1">Consigliato: scarica un backup prima di cancellare</p>
                  <p className="text-xs text-amber-700 mb-2">Salva un file JSON con tutti i tuoi dati. Potrai ripristinarli in futuro se necessario.</p>
                  <button
                    type="button"
                    onClick={downloadBackup}
                    disabled={backingUp}
                    className="px-3 py-1.5 bg-amber-600 hover:bg-amber-700 disabled:opacity-40 text-white rounded-md text-xs font-medium"
                    data-testid="download-backup-btn">
                    {backingUp ? "Esportazione in corso..." : downloadedBackup ? "✅ Backup scaricato — riscarica" : "📥 Scarica backup JSON"}
                  </button>
                </div>
              </div>
              <p className="text-sm font-bold text-red-700">
                Per confermare, digita esattamente <code className="bg-white px-2 py-0.5 rounded border border-red-300">RESET</code> qui sotto:
              </p>
              <input
                type="text"
                autoFocus
                value={confirmText}
                onChange={e => setConfirmText(e.target.value)}
                placeholder="Digita RESET"
                className="w-full px-3 py-2 border-2 border-red-300 rounded-md font-mono text-sm focus:outline-none focus:ring-2 focus:ring-red-500"
                data-testid="reset-confirm-input"
              />
              <label className="flex items-center gap-2 text-xs text-slate-700">
                <input type="checkbox" checked={resetCounters} onChange={e => setResetCounters(e.target.checked)} data-testid="reset-counters-checkbox" />
                Resetta anche i contatori di numerazione (DDT, FT, ORD ripartono da 1)
              </label>
              {confirmText === "RESET" && !downloadedBackup && (
                <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
                  ⚠️ Non hai ancora scaricato il backup. Sei sicuro di voler procedere senza?
                </p>
              )}
              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => { setOpen(false); setConfirmText(""); setDownloadedBackup(false); }}
                  className="px-4 py-2 border border-slate-300 hover:bg-slate-50 rounded-md text-sm">
                  Annulla
                </button>
                <button
                  type="button"
                  onClick={doReset}
                  disabled={confirmText !== "RESET" || loading}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-md text-sm font-medium"
                  data-testid="reset-execute-btn">
                  {loading ? "Cancellazione in corso..." : "CANCELLA TUTTO"}
                </button>
              </div>
            </div>
          )}

          {result && (
            <div className="border-2 border-emerald-300 rounded-lg p-4 bg-emerald-50" data-testid="reset-result">
              <p className="font-bold text-emerald-700 mb-2">✅ Operazione completata</p>
              <p className="text-sm text-slate-700 mb-3">{result.message}</p>
              <details className="text-xs">
                <summary className="cursor-pointer text-slate-600 hover:text-slate-900">Dettaglio per collezione ({result.total_deleted} record · {result.counters_reset} contatori)</summary>
                <table className="mt-2 w-full text-xs"><tbody>
                  {Object.entries(result.per_collection).map(([k, v]) => (
                    <tr key={k}><td className="py-0.5 font-mono">{k}</td><td className="text-right font-mono">{v}</td></tr>
                  ))}
                </tbody></table>
              </details>
              <button
                type="button"
                onClick={() => { setResult(null); setOpen(false); setConfirmText(""); window.location.reload(); }}
                className="mt-3 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-md text-sm">
                Ricarica pagina
              </button>
            </div>
          )}
        </div>
      </details>

      {/* Sezione Ripristino */}
      <RestoreBackup />
    </div>
  );
}

function RestoreBackup() {
  const [file, setFile] = React.useState(null);
  const [mode, setMode] = React.useState("merge");
  const [confirmText, setConfirmText] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [result, setResult] = React.useState(null);
  const [preview, setPreview] = React.useState(null);

  const onFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f); setResult(null); setPreview(null);
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
    setLoading(true);
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      const { data: res } = await api.post("/company/restore-operativo", { confirm: "RESTORE", mode, data });
      setResult(res);
      toast.success(`${res.total_inserted + res.total_updated} record ripristinati`);
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    finally { setLoading(false); }
  };

  return (
    <div className="mt-6" data-testid="restore-zone">
      <details className="rounded-lg border-2 border-amber-200 bg-amber-50/30 overflow-hidden">
        <summary className="px-5 py-3 cursor-pointer font-display font-bold text-amber-800 hover:bg-amber-100/40 select-none">
          📥 Ripristina backup JSON
        </summary>
        <div className="p-5 border-t border-amber-200 bg-white space-y-4">
          <p className="text-sm text-slate-700">
            Carica un file JSON esportato dal bottone "Scarica backup" e ripristina i dati nel tuo tenant.
          </p>

          <div>
            <label className="block text-xs font-mono uppercase tracking-wide text-slate-600 mb-1">File backup (.json)</label>
            <input type="file" accept="application/json,.json" onChange={onFile} data-testid="restore-file-input"
              className="block w-full text-sm border border-slate-200 rounded px-3 py-2 file:mr-3 file:py-1 file:px-3 file:rounded file:border-0 file:bg-indaco file:text-white file:cursor-pointer" />
          </div>

          {preview && (
            <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-xs">
              <p><b>Tenant nel backup:</b> <span className="font-mono">{preview.tenant_id || "—"}</span></p>
              <p><b>Esportato il:</b> {preview.exported_at?.slice(0, 19).replace("T", " ")}</p>
              <p><b>Totale record:</b> {preview.total}</p>
              <details className="mt-1"><summary className="cursor-pointer text-slate-500">Dettaglio collezioni</summary>
                <table className="mt-1 w-full"><tbody>
                  {Object.entries(preview.counts).map(([k, v]) => v > 0 && (
                    <tr key={k}><td className="font-mono py-0.5">{k}</td><td className="text-right font-mono">{v}</td></tr>
                  ))}
                </tbody></table>
              </details>
            </div>
          )}

          {file && !result && (
            <div className="space-y-3">
              <div>
                <p className="text-sm font-bold text-slate-700 mb-2">Modalità ripristino:</p>
                <div className="flex gap-2">
                  <button type="button" onClick={() => setMode("merge")}
                    className={`flex-1 border-2 rounded-md p-2 text-xs text-left ${mode === "merge" ? "border-indaco bg-indaco/5" : "border-slate-200"}`}
                    data-testid="restore-mode-merge">
                    <p className="font-bold">🔀 Merge (consigliato)</p>
                    <p className="text-slate-500 mt-0.5">I record esistenti vengono sovrascritti per ID. I record non presenti nel backup restano.</p>
                  </button>
                  <button type="button" onClick={() => setMode("replace")}
                    className={`flex-1 border-2 rounded-md p-2 text-xs text-left ${mode === "replace" ? "border-red-500 bg-red-50" : "border-slate-200"}`}
                    data-testid="restore-mode-replace">
                    <p className="font-bold">🗑️ Replace</p>
                    <p className="text-slate-500 mt-0.5">Cancella TUTTI i dati esistenti, poi importa quelli del backup. Più aggressivo.</p>
                  </button>
                </div>
              </div>

              <div>
                <p className="text-sm font-bold text-amber-800">
                  Per confermare, digita esattamente <code className="bg-white px-2 py-0.5 rounded border border-amber-300">RESTORE</code> qui sotto:
                </p>
                <input type="text" value={confirmText} onChange={e => setConfirmText(e.target.value)}
                  placeholder="Digita RESTORE"
                  className="mt-1 w-full px-3 py-2 border-2 border-amber-300 rounded-md font-mono text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                  data-testid="restore-confirm-input" />
              </div>

              <button type="button" onClick={doRestore} disabled={confirmText !== "RESTORE" || loading}
                className="px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-md text-sm font-medium"
                data-testid="restore-execute-btn">
                {loading ? "Ripristino in corso..." : "RIPRISTINA"}
              </button>
            </div>
          )}

          {result && (
            <div className="border-2 border-emerald-300 rounded-lg p-4 bg-emerald-50" data-testid="restore-result">
              <p className="font-bold text-emerald-700 mb-2">✅ Ripristino completato</p>
              <p className="text-sm text-slate-700 mb-2">{result.message}</p>
              <p className="text-xs text-slate-500">Modalità: <span className="font-mono">{result.mode}</span></p>
              <button type="button" onClick={() => window.location.reload()}
                className="mt-3 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-md text-sm">
                Ricarica pagina
              </button>
            </div>
          )}
        </div>
      </details>
    </div>
  );
}


function CloudBackups() {
  const [snapshots, setSnapshots] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [creating, setCreating] = React.useState(false);
  const [retentionDays, setRetentionDays] = React.useState(7);
  const [restoreState, setRestoreState] = React.useState({ open: false, snapshotId: null, mode: "merge", confirmText: "", running: false });

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/company/backup/cloud/list");
      setSnapshots(data.snapshots || []);
      setRetentionDays(data.retention_days || 7);
    } catch (e) {
      toast.error("Errore caricamento snapshot cloud");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => { load(); }, [load]);

  const createNow = async () => {
    setCreating(true);
    try {
      const { data } = await api.post("/company/backup/cloud");
      toast.success(`Snapshot creato (${(data.snapshot.size_bytes / 1024).toFixed(0)} KB · ${data.snapshot.total_records} record)`);
      if (data.pruned > 0) toast.info(`${data.pruned} snapshot più vecchi rimossi per retention`);
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore creazione snapshot");
    } finally { setCreating(false); }
  };

  const askRestore = (snapshotId) => {
    setRestoreState({ open: true, snapshotId, mode: "merge", confirmText: "", running: false });
  };

  const doRestore = async () => {
    const { snapshotId, mode, confirmText } = restoreState;
    if (confirmText !== "RESTORE" || !snapshotId) return;
    setRestoreState(s => ({ ...s, running: true }));
    try {
      const { data } = await api.post(`/company/backup/cloud/${snapshotId}/restore`, { confirm: "RESTORE", mode });
      toast.success(`${data.total_inserted + data.total_updated} record ripristinati`);
      setRestoreState({ open: false, snapshotId: null, mode: "merge", confirmText: "", running: false });
      setTimeout(() => window.location.reload(), 1200);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore ripristino");
      setRestoreState(s => ({ ...s, running: false }));
    }
  };

  const deleteSnapshot = async (snapshotId) => {
    if (!window.confirm("Eliminare definitivamente questo snapshot?")) return;
    try {
      await api.delete(`/company/backup/cloud/${snapshotId}`);
      toast.success("Snapshot eliminato");
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore");
    }
  };

  const fmtDate = (iso) => {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  };
  const fmtSize = (bytes) => {
    if (!bytes && bytes !== 0) return "—";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
  };

  return (
    <div className="mt-6 max-w-4xl mx-auto" data-testid="cloud-backups">
      <details className="rounded-lg border-2 border-celeste/40 bg-celeste/5 overflow-hidden" open>
        <summary className="px-5 py-3 cursor-pointer font-display font-bold text-indaco hover:bg-celeste/10 select-none flex items-center justify-between">
          <span>☁️ Snapshot Cloud — backup automatici giornalieri</span>
          <span className="text-xs font-mono text-slate-500">retention: {retentionDays} snapshot</span>
        </summary>
        <div className="p-5 border-t border-celeste/40 bg-white space-y-4">
          <div className="text-sm text-slate-700 space-y-1">
            <p>I tuoi dati vengono salvati ogni giorno alle <b>03:00 UTC</b> su archiviazione cloud sicura.</p>
            <p className="text-xs text-slate-500">
              Vengono conservati gli ultimi <b>{retentionDays} snapshot</b> per tenant; i più vecchi vengono rimossi automaticamente.
              Puoi anche creare uno snapshot manuale in qualunque momento.
            </p>
          </div>

          <button
            type="button"
            onClick={createNow}
            disabled={creating}
            className="px-4 py-2 bg-indaco hover:bg-indaco-dark disabled:opacity-40 text-white rounded-md text-sm font-medium"
            data-testid="cloud-backup-create-btn">
            {creating ? "Creazione in corso…" : "📸 Crea snapshot ora"}
          </button>

          <div className="rounded-md border border-slate-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-600">
                <tr>
                  <th className="text-left px-3 py-2">Data</th>
                  <th className="text-left px-3 py-2">Origine</th>
                  <th className="text-right px-3 py-2">Record</th>
                  <th className="text-right px-3 py-2">Dimensione</th>
                  <th className="text-right px-3 py-2">Azioni</th>
                </tr>
              </thead>
              <tbody data-testid="cloud-backup-list">
                {loading ? (
                  <tr><td colSpan={5} className="text-center py-4 text-slate-400 font-mono text-xs">Caricamento…</td></tr>
                ) : snapshots.length === 0 ? (
                  <tr><td colSpan={5} className="text-center py-6 text-slate-400 text-sm">Nessuno snapshot disponibile. Creane uno manualmente o attendi il run automatico delle 03:00 UTC.</td></tr>
                ) : (
                  snapshots.map(s => (
                    <tr key={s.id} className="border-t border-slate-100 hover:bg-slate-50/60" data-testid={`cloud-backup-row-${s.id}`}>
                      <td className="px-3 py-2 font-mono text-xs">{fmtDate(s.created_at)}</td>
                      <td className="px-3 py-2 text-xs">
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${s.source === "auto" ? "bg-celeste/15 text-indaco" : "bg-amber-100 text-amber-700"}`}>
                          {s.source === "auto" ? "🤖 auto" : "👤 manuale"}
                        </span>
                        {s.created_by && s.source !== "auto" && (
                          <span className="ml-2 text-slate-400 font-mono">{s.created_by}</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-xs">{s.total_records}</td>
                      <td className="px-3 py-2 text-right font-mono text-xs">{fmtSize(s.size_bytes)}</td>
                      <td className="px-3 py-2 text-right space-x-2 whitespace-nowrap">
                        <button
                          type="button"
                          onClick={() => askRestore(s.id)}
                          className="px-2 py-1 text-xs bg-emerald-600 hover:bg-emerald-700 text-white rounded"
                          data-testid={`cloud-backup-restore-btn-${s.id}`}>
                          Ripristina
                        </button>
                        <button
                          type="button"
                          onClick={() => deleteSnapshot(s.id)}
                          className="px-2 py-1 text-xs bg-red-500 hover:bg-red-600 text-white rounded"
                          data-testid={`cloud-backup-delete-btn-${s.id}`}>
                          Elimina
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {restoreState.open && (
            <div className="mt-2 border-2 border-emerald-300 rounded-lg p-4 bg-emerald-50 space-y-3" data-testid="cloud-backup-restore-dialog">
              <p className="text-sm font-bold text-emerald-800">Ripristino da snapshot cloud</p>
              <div className="flex gap-2">
                <button type="button" onClick={() => setRestoreState(s => ({ ...s, mode: "merge" }))}
                  className={`flex-1 border-2 rounded-md p-2 text-xs text-left ${restoreState.mode === "merge" ? "border-indaco bg-white" : "border-slate-200 bg-white/60"}`}
                  data-testid="cloud-restore-mode-merge">
                  <p className="font-bold">🔀 Merge (consigliato)</p>
                  <p className="text-slate-500 mt-0.5">Sovrascrive i record per ID. I record nuovi non vengono toccati.</p>
                </button>
                <button type="button" onClick={() => setRestoreState(s => ({ ...s, mode: "replace" }))}
                  className={`flex-1 border-2 rounded-md p-2 text-xs text-left ${restoreState.mode === "replace" ? "border-red-500 bg-white" : "border-slate-200 bg-white/60"}`}
                  data-testid="cloud-restore-mode-replace">
                  <p className="font-bold">🗑️ Replace</p>
                  <p className="text-slate-500 mt-0.5">Cancella TUTTI i dati operativi del tenant, poi importa lo snapshot.</p>
                </button>
              </div>
              <div>
                <p className="text-xs font-bold text-emerald-800">
                  Digita <code className="bg-white px-2 py-0.5 rounded border border-emerald-300">RESTORE</code> per confermare:
                </p>
                <input type="text" value={restoreState.confirmText}
                  onChange={e => setRestoreState(s => ({ ...s, confirmText: e.target.value }))}
                  placeholder="Digita RESTORE"
                  className="mt-1 w-full px-3 py-2 border-2 border-emerald-300 rounded-md font-mono text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  data-testid="cloud-restore-confirm-input" />
              </div>
              <div className="flex gap-2">
                <button type="button"
                  onClick={() => setRestoreState({ open: false, snapshotId: null, mode: "merge", confirmText: "", running: false })}
                  className="px-4 py-2 border border-slate-300 hover:bg-slate-50 rounded-md text-sm">
                  Annulla
                </button>
                <button type="button"
                  onClick={doRestore}
                  disabled={restoreState.confirmText !== "RESTORE" || restoreState.running}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-md text-sm font-medium"
                  data-testid="cloud-restore-execute-btn">
                  {restoreState.running ? "Ripristino in corso…" : "RIPRISTINA"}
                </button>
              </div>
            </div>
          )}
        </div>
      </details>
    </div>
  );
}
