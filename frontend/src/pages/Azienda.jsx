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

    </div>
  );
}
