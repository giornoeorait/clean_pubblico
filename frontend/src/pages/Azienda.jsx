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
  { k: "iban",             label: "IBAN",                    required: false, placeholder: "IT60 X 05428 11101 00000 0123456" },
  { k: "email",            label: "Email",                   required: true,  placeholder: "info@tuaazienda.it" },
  { k: "pec",              label: "PEC",                     required: false, placeholder: "azienda@pec.it" },
  { k: "codice_sdi",       label: "Codice destinatario SDI", required: false, placeholder: "0000000 oppure ABC1234" },
  { k: "telefono",         label: "Telefono",                required: true,  placeholder: "+39 02 1234567" },
  { k: "sito_web",         label: "Sito internet",           required: false, placeholder: "https://tuaazienda.it" },
  { k: "regime_fiscale",   label: "Regime fiscale (Fattura elettronica)", required: false, placeholder: "RF01", options: ["RF01","RF02","RF04","RF05","RF06","RF07","RF08","RF09","RF10","RF11","RF12","RF13","RF14","RF15","RF16","RF17","RF18","RF19"] },
  { k: "iva_default_pct",  label: "Aliquota IVA di default (%)", required: false, placeholder: "22", type: "number" },
];

const SEDE_FIELDS = [
  { k: "indirizzo", label: "Indirizzo (via e civico)", required: true, placeholder: "Via Roma 123", colSpan: "md:col-span-2" },
  { k: "cap",       label: "CAP",                     required: true, placeholder: "20100", maxLength: 5, colSpan: "" },
  { k: "comune",    label: "Comune",                  required: true, placeholder: "Milano", colSpan: "" },
  { k: "provincia", label: "Provincia",               required: true, placeholder: "MI", maxLength: 2, colSpan: "", upper: true },
];

const REQUIRED_KEYS = [
  ...FIELDS.filter(f => f.required).map(f => f.k),
  ...SEDE_FIELDS.filter(f => f.required).map(f => f.k),
];

const ALL_FIELDS_KEYS = [...FIELDS.map(f => f.k), ...SEDE_FIELDS.map(f => f.k)];

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

  const missingRequired = [...FIELDS, ...SEDE_FIELDS]
    .filter(f => f.required && !(form[f.k] || "").trim())
    .map(f => f.label);
  const isComplete = missingRequired.length === 0;

  const save = async () => {
    if (!isComplete) {
      toast.error(`Campi obbligatori mancanti: ${missingRequired.join(", ")}`);
      return;
    }
    setSaving(true);
    try {
      const payload = Object.fromEntries(ALL_FIELDS_KEYS.map(k => [k, form[k] || ""]));
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
              const val = form[f.k] != null ? String(form[f.k]) : "";
              const missing = f.required && !val.trim();
              return (
                <div key={f.k}>
                  <Label>
                    {f.label}
                    {f.required && <span className="text-red-500 ml-0.5">*</span>}
                  </Label>
                  {f.options ? (
                    <select
                      value={val || (f.options[0] || "")}
                      onChange={e => update(f.k, e.target.value)}
                      data-testid={`azienda-${f.k}`}
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indaco">
                      {f.options.map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  ) : (
                    <Input
                      type={f.type || "text"}
                      value={val}
                      onChange={e => update(f.k, e.target.value)}
                      placeholder={f.placeholder}
                      maxLength={f.maxLength}
                      data-testid={`azienda-${f.k}`}
                      className={missing ? "border-amber-300" : ""}
                    />
                  )}
                </div>
              );
            })}
          </div>

          {/* Sede legale (Fatturazione Elettronica) */}
          <div className="mt-6 border-2 border-amber-300 rounded-lg p-4 bg-amber-50/60" data-testid="azienda-sede-section">
            <h4 className="font-display font-bold text-sm text-amber-900 flex items-center gap-2 mb-3">
              <ImageSquare size={16} className="text-amber-700" weight="duotone" />
              Sede legale <span className="text-[11px] font-mono uppercase text-amber-700">(richiesti per Fatturazione Elettronica)</span>
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {SEDE_FIELDS.map(f => {
                const val = form[f.k] != null ? String(form[f.k]) : "";
                const missing = f.required && !val.trim();
                return (
                  <div key={f.k} className={f.colSpan || ""}>
                    <Label className="text-amber-900">
                      {f.label}
                      {f.required && <span className="text-red-500 ml-0.5">*</span>}
                    </Label>
                    <Input
                      type="text"
                      value={val}
                      onChange={e => update(f.k, f.upper ? e.target.value.toUpperCase().replace(/[^A-Z]/g, "") : e.target.value)}
                      placeholder={f.placeholder}
                      maxLength={f.maxLength}
                      data-testid={`azienda-${f.k}`}
                      className={`${missing ? "border-red-300 bg-red-50/30" : "border-amber-300"} ${f.k === "cap" || f.k === "provincia" ? "font-mono" : ""}`}
                    />
                  </div>
                );
              })}
            </div>
            <p className="text-[11px] text-amber-700 mt-2">
              Senza questi 3 campi (CAP, Comune, Provincia) gli XML Fattura Elettronica saranno rifiutati dallo SdI.
            </p>
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

      <NumerazioneSection />

    </div>
  );
}

function NumerazioneSection() {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [edited, setEdited] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/company/numerazione");
      setEntries(data.entries || []);
      setEdited({});
    } catch (e) { toast.error("Errore caricamento numerazione"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const updateField = (key, field, value) => {
    setEdited(prev => ({ ...prev, [key]: { ...(prev[key] || {}), [field]: value } }));
  };

  const valueFor = (key, field) => {
    if (edited[key] && field in edited[key]) return edited[key][field];
    const e = entries.find(x => x.key === key);
    if (!e) return field === "seq" ? 0 : "";
    return field === "seq" ? e.current_seq : (e.suffix || "");
  };

  const hasChanges = Object.keys(edited).length > 0;

  const save = async () => {
    if (!hasChanges) return;
    setSaving(true);
    try {
      const payload = {
        entries: entries.map(e => ({
          key: e.key,
          seq: Number(valueFor(e.key, "seq")),
          suffix: String(valueFor(e.key, "suffix") || ""),
        })),
      };
      const { data } = await api.put("/company/numerazione", payload);
      setEntries(data.entries || []);
      setEdited({});
      toast.success("Numerazione aggiornata");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore salvataggio");
    } finally { setSaving(false); }
  };

  return (
    <div className="kpi-card" data-testid="numerazione-section">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <div className="overline text-slate-400">Documenti · numerazione</div>
          <h3 className="font-display text-lg font-bold flex items-center gap-2 mt-0.5">
            Numerazione documenti
          </h3>
          <p className="text-sm text-slate-500 mt-1">
            Imposta il numero di partenza (utile se hai già emesso documenti quest'anno) e un eventuale suffisso (es. <code className="font-mono bg-slate-100 px-1">/L</code>).
            La prossima emissione sarà <code className="font-mono bg-slate-100 px-1">N+1</code>.
          </p>
        </div>
        <button
          type="button"
          onClick={save}
          disabled={!hasChanges || saving}
          className="px-4 py-2 bg-indaco hover:bg-indaco-dark disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-md text-sm font-medium whitespace-nowrap"
          data-testid="numerazione-save-btn">
          {saving ? "Salvataggio…" : "Salva numerazione"}
        </button>
      </div>

      {loading ? (
        <p className="text-xs text-slate-400 font-mono">Caricamento…</p>
      ) : (
        <div className="rounded-md border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="text-left px-3 py-2 font-medium">Documento</th>
                <th className="text-left px-3 py-2 font-medium">Prefisso</th>
                <th className="text-right px-3 py-2 font-medium">Ultimo numero emesso</th>
                <th className="text-left px-3 py-2 font-medium">Suffisso</th>
                <th className="text-left px-3 py-2 font-medium">Anteprima prossimo</th>
              </tr>
            </thead>
            <tbody data-testid="numerazione-table">
              {entries.map(e => {
                const seqVal = valueFor(e.key, "seq");
                const suffixVal = valueFor(e.key, "suffix");
                const nextSeq = Number(seqVal) + 1;
                const year = new Date().getFullYear();
                const preview = `${e.prefix}-${year}-${String(nextSeq).padStart(5, "0")}${suffixVal || ""}`;
                const changed = !!edited[e.key];
                return (
                  <tr key={e.key} className={`border-t border-slate-100 ${changed ? "bg-amber-50/40" : ""}`}>
                    <td className="px-3 py-2 font-medium text-slate-900">{e.label}</td>
                    <td className="px-3 py-2 font-mono text-xs text-slate-500">{e.prefix}-</td>
                    <td className="px-3 py-2">
                      <Input
                        type="number"
                        min={e.current_seq}
                        value={seqVal}
                        onChange={ev => updateField(e.key, "seq", ev.target.value)}
                        className="h-8 text-right font-mono w-24 ml-auto"
                        data-testid={`numerazione-seq-${e.key}`}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <Input
                        value={suffixVal}
                        onChange={ev => updateField(e.key, "suffix", ev.target.value)}
                        placeholder="(nessuno)"
                        maxLength={8}
                        className="h-8 font-mono w-24"
                        data-testid={`numerazione-suffix-${e.key}`}
                      />
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-indaco">{preview}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-slate-500 mt-2">
        ℹ️ Il numero di partenza non può essere abbassato (per evitare duplicati). Per ripartire da 1 usa il reset operativo in <b>Backup &amp; Dati</b>.
      </p>
    </div>
  );
}
