import React, { useState } from "react";
import api from "../lib/api";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { toast } from "sonner";
import {
  UploadSimple, FileXls, CheckCircle, Warning, ArrowsClockwise, X,
  ListChecks, Sparkle,
} from "@phosphor-icons/react";

/* ------------------------------------------------------------------ */
/*  Status badges                                                      */
/* ------------------------------------------------------------------ */

const STATUS_META = {
  ok:        { label: "OK",        cls: "bg-emerald-100 text-emerald-700 border-emerald-200", icon: CheckCircle },
  warning:   { label: "Warning",   cls: "bg-amber-100 text-amber-700 border-amber-200",       icon: Warning },
  duplicate: { label: "Duplicato", cls: "bg-slate-200 text-slate-600 border-slate-300",       icon: ArrowsClockwise },
  skip:      { label: "Saltato",   cls: "bg-red-100 text-red-700 border-red-200",             icon: X },
};

function StatusBadge({ status }) {
  const m = STATUS_META[status] || STATUS_META.skip;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border ${m.cls}`}>
      <m.icon size={11} weight="fill" /> {m.label}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/*  Dialog                                                             */
/* ------------------------------------------------------------------ */

export default function ImportClientiDialog({ onImported }) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState(null);
  const [parsing, setParsing] = useState(false);
  const [importing, setImporting] = useState(false);
  const [preview, setPreview] = useState(null);
  const [includeWarnings, setIncludeWarnings] = useState(true);
  const [done, setDone] = useState(null);
  const [dragOver, setDragOver] = useState(false);

  const reset = () => {
    setFile(null); setPreview(null); setDone(null); setIncludeWarnings(true);
  };

  const onClose = (o) => { setOpen(o); if (!o) reset(); };

  const handleFile = async (f) => {
    if (!f) return;
    setFile(f); setPreview(null); setDone(null);
    setParsing(true);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const { data } = await api.post("/imports/clienti/preview", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setPreview(data);
      toast.success(`File analizzato: ${data.counts.total} righe trovate`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore durante l'analisi del file");
      setFile(null);
    } finally { setParsing(false); }
  };

  const doImport = async () => {
    if (!preview) return;
    setImporting(true);
    try {
      const accept = ["ok"];
      if (includeWarnings) accept.push("warning");
      const payload = {
        clienti: preview.rows.filter(r => accept.includes(r.status)),
        accept_statuses: accept,
      };
      const { data } = await api.post("/imports/clienti/commit", payload);
      setDone(data);
      toast.success(data.message);
      if (onImported) onImported();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore durante l'import");
    } finally { setImporting(false); }
  };

  const onDrop = (e) => {
    e.preventDefault(); setDragOver(false);
    const f = e.dataTransfer?.files?.[0];
    if (f) handleFile(f);
  };

  const counts = preview?.counts || { total: 0, ok: 0, warning: 0, duplicate: 0, skip: 0 };
  const toImport = counts.ok + (includeWarnings ? counts.warning : 0);

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogTrigger asChild>
        <Button variant="outline" className="border-indaco/30 text-indaco hover:bg-indaco/5" data-testid="import-clienti-btn">
          <UploadSimple size={16} weight="duotone" className="mr-1.5" />
          Importa da Excel
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto" data-testid="import-clienti-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileXls size={22} weight="duotone" className="text-indaco" />
            Importa clienti da Excel
          </DialogTitle>
          <DialogDescription>
            Carica un file <code className="font-mono text-xs">.xlsx</code>, <code className="font-mono text-xs">.xls</code> o <code className="font-mono text-xs">.csv</code> esportato dal tuo vecchio gestionale. Le intestazioni vengono mappate automaticamente sui campi dell'anagrafica clienti.
          </DialogDescription>
        </DialogHeader>

        {/* Step 1: upload */}
        {!preview && !done && (
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            className={`mt-4 rounded-xl border-2 border-dashed p-10 text-center transition-colors cursor-pointer ${dragOver ? "border-indaco bg-indaco/5" : "border-slate-300 bg-slate-50 hover:border-indaco/50"}`}
            onClick={() => document.getElementById("import-file-input")?.click()}
            data-testid="import-dropzone"
          >
            <UploadSimple size={42} weight="duotone" className="mx-auto text-indaco mb-3" />
            <p className="font-display font-bold text-slate-900">Trascina qui il file o clicca per selezionarlo</p>
            <p className="text-sm text-slate-500 mt-1">Formati supportati: <code className="font-mono">.xlsx</code>, <code className="font-mono">.xls</code>, <code className="font-mono">.csv</code> · max 5 MB · 2.000 righe</p>
            <input
              id="import-file-input"
              type="file"
              accept=".xlsx,.xls,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              className="hidden"
              onChange={(e) => handleFile(e.target.files?.[0])}
              data-testid="import-file-input"
            />
            {parsing && (
              <div className="mt-4 inline-flex items-center gap-2 text-indaco text-sm">
                <ArrowsClockwise size={14} className="animate-spin" />
                Analisi in corso…
              </div>
            )}
          </div>
        )}

        {/* Step 2: preview */}
        {preview && !done && (
          <div className="mt-4 space-y-4">
            {/* Summary chips */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <SummaryChip count={counts.ok}        label="Pronti"     accent="emerald" icon={CheckCircle} />
              <SummaryChip count={counts.warning}   label="Warning"    accent="amber"   icon={Warning} />
              <SummaryChip count={counts.duplicate} label="Duplicati"  accent="slate"   icon={ArrowsClockwise} />
              <SummaryChip count={counts.skip}      label="Da saltare" accent="red"     icon={X} />
            </div>

            <div className="rounded-md bg-slate-50 border border-slate-200 p-3 text-xs text-slate-600">
              <div className="flex items-center gap-2 font-medium text-slate-700 mb-1">
                <ListChecks size={14} weight="duotone" /> Mapping colonne rilevato
              </div>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(preview.columns_detected || {}).map(([excel, field]) => (
                  <span key={excel} className="inline-flex items-center gap-1 bg-white border border-slate-200 rounded px-2 py-0.5 font-mono">
                    <span className="text-slate-500">{excel}</span> → <span className="text-indaco">{field}</span>
                  </span>
                ))}
              </div>
            </div>

            {/* Settings */}
            <label className="flex items-start gap-2 text-sm text-slate-700 bg-amber-50/40 border border-amber-200 rounded-md p-3 cursor-pointer">
              <input
                type="checkbox"
                checked={includeWarnings}
                onChange={(e) => setIncludeWarnings(e.target.checked)}
                className="mt-0.5 accent-indaco"
                data-testid="import-include-warnings"
              />
              <span>
                <b>Importa anche le righe con warning</b>
                <span className="block text-xs text-slate-500">
                  Verranno applicati placeholder per i campi mancanti (es. email/telefono).
                  Potrai modificarli singolarmente dopo l'import.
                </span>
              </span>
            </label>

            {/* Preview table */}
            <div className="rounded-md border border-slate-200 overflow-hidden">
              <div className="max-h-80 overflow-y-auto">
                <table className="w-full text-xs">
                  <thead className="bg-slate-50 sticky top-0">
                    <tr className="text-slate-500 uppercase tracking-wide">
                      <th className="text-left px-3 py-2 font-medium">#</th>
                      <th className="text-left px-3 py-2 font-medium">Stato</th>
                      <th className="text-left px-3 py-2 font-medium">Denominazione</th>
                      <th className="text-left px-3 py-2 font-medium">Ragione sociale</th>
                      <th className="text-left px-3 py-2 font-medium">P.IVA</th>
                      <th className="text-left px-3 py-2 font-medium">Email</th>
                      <th className="text-left px-3 py-2 font-medium">Note</th>
                    </tr>
                  </thead>
                  <tbody data-testid="import-preview-table">
                    {preview.rows.map((r) => (
                      <tr key={r.row_number} className="border-t border-slate-100 hover:bg-slate-50/60">
                        <td className="px-3 py-1.5 font-mono text-slate-400">{r.row_number}</td>
                        <td className="px-3 py-1.5"><StatusBadge status={r.status} /></td>
                        <td className="px-3 py-1.5 text-slate-900 max-w-[180px] truncate" title={r.cliente.denominazione_struttura}>{r.cliente.denominazione_struttura || "—"}</td>
                        <td className="px-3 py-1.5 text-slate-700 max-w-[160px] truncate" title={r.cliente.ragione_sociale}>{r.cliente.ragione_sociale || "—"}</td>
                        <td className="px-3 py-1.5 font-mono text-slate-600">{r.cliente.partita_iva || "—"}</td>
                        <td className="px-3 py-1.5 text-slate-500 max-w-[150px] truncate" title={r.cliente.email}>{r.cliente.email}</td>
                        <td className="px-3 py-1.5 text-slate-400 max-w-[140px] truncate" title={r.reasons.join(" · ")}>{r.reasons.join(" · ") || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Actions */}
            <div className="flex flex-wrap gap-2 pt-2 border-t border-slate-100 justify-between items-center">
              <Button variant="outline" onClick={reset} data-testid="import-reset-btn">
                <X size={14} className="mr-1" /> Cambia file
              </Button>
              <Button
                onClick={doImport}
                disabled={importing || toImport === 0}
                className="bg-indaco hover:bg-indaco-dark"
                data-testid="import-execute-btn">
                <Sparkle size={14} weight="duotone" className="mr-1.5" />
                {importing ? "Importazione in corso…" : `Importa ${toImport} clienti`}
              </Button>
            </div>
          </div>
        )}

        {/* Step 3: done */}
        {done && (
          <div className="mt-4 rounded-xl border-2 border-emerald-300 bg-emerald-50/60 p-6 text-center" data-testid="import-result">
            <CheckCircle size={48} weight="duotone" className="mx-auto text-emerald-600 mb-3" />
            <div className="font-display text-xl font-bold text-emerald-700">Import completato</div>
            <p className="text-sm text-slate-700 mt-1">{done.message}</p>
            {done.errors?.length > 0 && (
              <div className="mt-3 text-left bg-white rounded-md border border-red-200 p-3 text-xs">
                <div className="font-bold text-red-700 mb-1">Errori ({done.errors.length}):</div>
                <ul className="space-y-0.5 text-slate-600">
                  {done.errors.slice(0, 8).map((e, i) => (
                    <li key={i} className="font-mono">· {e.denominazione || "—"}: {e.error}</li>
                  ))}
                </ul>
              </div>
            )}
            <Button onClick={() => onClose(false)} className="mt-4 bg-emerald-600 hover:bg-emerald-700" data-testid="import-close-btn">
              Chiudi
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

/* ------------------------------------------------------------------ */
/*  Small summary chip                                                 */
/* ------------------------------------------------------------------ */

function SummaryChip({ count, label, accent, icon: Icon }) {
  const accents = {
    emerald: "bg-emerald-50 border-emerald-200 text-emerald-700",
    amber:   "bg-amber-50 border-amber-200 text-amber-700",
    slate:   "bg-slate-50 border-slate-200 text-slate-600",
    red:     "bg-red-50 border-red-200 text-red-700",
  };
  return (
    <div className={`rounded-lg border p-3 ${accents[accent]}`}>
      <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide font-medium">
        <Icon size={12} weight="fill" /> {label}
      </div>
      <div className="font-display text-2xl font-bold mt-1 leading-none">{count}</div>
    </div>
  );
}
