import React, { useCallback, useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { Receipt, CheckCircle, Plus, Eye, Trash, CurrencyEur, FilePdf, FileXls, Package, CalendarBlank, ShieldCheck } from "@phosphor-icons/react";
import { Popover, PopoverContent, PopoverTrigger } from "../components/ui/popover";
import { clientePrimary, docPrimary, docSecondary } from "../lib/clienteLabel";
import { toast } from "sonner";

export default function Fatture() {
  const [list, setList] = useState([]);
  const [clienti, setClienti] = useState([]);
  const [filterStato, setFilterStato] = useState("all");

  // New fattura dialog
  const [genOpen, setGenOpen] = useState(false);
  const [genCli, setGenCli] = useState("");
  const [genDdts, setGenDdts] = useState([]);
  const [genSelected, setGenSelected] = useState(new Set());
  const [ivaPct, setIvaPct] = useState(22);
  const [scadenza, setScadenza] = useState("");

  // Detail
  const [detail, setDetail] = useState(null);

  const fetchAll = useCallback(async () => {
    const q = filterStato !== "all" ? `?stato_incasso=${filterStato}` : "";
    const [f, c] = await Promise.all([api.get(`/fatture${q}`), api.get("/clienti")]);
    setList(f.data); setClienti(c.data);
  }, [filterStato]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const loadFatturabili = async (cliId) => {
    try {
      const { data } = await api.get(`/fatture/fatturabili?cliente_id=${cliId}`);
      setGenDdts(data.ddts);
      setGenSelected(new Set(data.ddts.map(d => d.id))); // select all by default
    } catch { setGenDdts([]); setGenSelected(new Set()); }
  };

  useEffect(() => { if (genCli) loadFatturabili(genCli); else { setGenDdts([]); setGenSelected(new Set()); } }, [genCli]);

  const toggleDdt = (id) => {
    setGenSelected(s => {
      const ns = new Set(s);
      if (ns.has(id)) ns.delete(id); else ns.add(id);
      return ns;
    });
  };

  const imponibileSel = genDdts.filter(d => genSelected.has(d.id)).reduce((s, d) => s + d.imponibile, 0);
  const ivaSel = imponibileSel * ivaPct / 100;
  const totaleSel = imponibileSel + ivaSel;

  const generate = async () => {
    if (genSelected.size === 0) { toast.error("Seleziona almeno un DDT"); return; }
    try {
      const { data } = await api.post("/fatture", {
        cliente_id: genCli,
        ddt_ids: Array.from(genSelected),
        iva_pct: parseFloat(ivaPct),
        scadenza: scadenza || undefined,
      });
      toast.success(`Fattura ${data.numero} generata — € ${data.totale.toFixed(2)}`);
      setGenOpen(false); setGenCli(""); setScadenza(""); fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const openDetail = async (f) => {
    const { data } = await api.get(`/fatture/${f.id}`); setDetail(data);
  };

  const incassa = async (f) => {
    try { await api.post(`/fatture/${f.id}/incassa`, { metodo: "bonifico" }); toast.success("Incassata"); fetchAll(); }
    catch (e) { toast.error(e.response?.data?.detail); }
  };

  const delFattura = async (f) => {
    if (!window.confirm(`Eliminare ${f.numero}? I DDT torneranno fatturabili.`)) return;
    try { await api.delete(`/fatture/${f.id}`); toast.success("Eliminata"); fetchAll(); }
    catch (e) { toast.error(e.response?.data?.detail); }
  };

  const openPdf = async (f) => {
    try {
      const res = await api.get(`/fatture/${f.id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      window.open(url, "_blank");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore PDF");
    }
  };

  const downloadXmlPa = async (f) => {
    try {
      const res = await api.get(`/fatture/${f.id}/xml`, { responseType: "blob" });
      const disp = res.headers["content-disposition"] || "";
      const m = disp.match(/filename="?([^";]+)"?/);
      const filename = m ? m[1] : `${f.numero}.xml`;
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = filename; a.click();
      URL.revokeObjectURL(url);
      toast.success("XML Fattura Elettronica scaricato (validato XSD)");
    } catch (e) {
      // Estrai eventuali errori di validazione SdI dal blob
      let detail = null;
      if (e.response?.data instanceof Blob) {
        try { detail = JSON.parse(await e.response.data.text()).detail; } catch { /* ignore */ }
      } else if (e.response?.data?.detail) {
        detail = e.response.data.detail;
      }
      if (detail && typeof detail === "object" && Array.isArray(detail.errors)) {
        const lines = detail.errors.slice(0, 6).map(er => `• ${er.message}`).join("\n");
        toast.error(`Fattura ${f.numero} — ${detail.errors.length} errore/i:\n${lines}`, {
          duration: 12000,
          style: { whiteSpace: "pre-line", maxWidth: "500px" },
        });
        // eslint-disable-next-line no-console
        console.warn("[XML SdI Validation]", detail.errors);
      } else {
        toast.error(typeof detail === "string" ? detail : "Errore generazione XML");
      }
    }
  };

  const validateXml = async (f) => {
    try {
      const { data } = await api.post(`/fatture/${f.id}/validate`);
      if (data.ok) {
        toast.success(`Fattura ${f.numero} conforme SdI ✓`, { duration: 5000 });
      } else {
        const lines = data.errors.slice(0, 6).map(er => `• ${er.message}`).join("\n");
        toast.error(`Fattura ${f.numero} — ${data.errors.length} errore/i:\n${lines}`, {
          duration: 12000,
          style: { whiteSpace: "pre-line", maxWidth: "500px" },
        });
      }
    } catch (e) {
      toast.error("Errore validazione: " + (e.response?.data?.detail || "—"));
    }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Contabilità"
        title="Fatturazione"
        subtitle="Genera fatture riepilogative da DDT non fatturati. Gestisci incassi e sospesi."
        actions={
          <div className="flex gap-2">
            <BulkXmlExport />
            <Button onClick={() => setGenOpen(true)} className="bg-indaco hover:bg-indaco-dark" data-testid="new-fattura-btn">
              <Plus size={16} className="mr-1" />Nuova fattura
            </Button>
          </div>
        }
      />

      <div className="flex gap-2 mb-4">
        {[["all", "Tutte"], ["da_incassare", "Da incassare"], ["incassata", "Incassate"]].map(([k, l]) => (
          <button key={k} onClick={() => setFilterStato(k)} className={`px-3 py-1.5 text-xs font-semibold rounded-md ${filterStato === k ? "bg-indaco text-white" : "bg-white border border-slate-200 text-slate-600"}`} data-testid={`fatt-filter-${k}`}>{l}</button>
        ))}
      </div>

      <div className="kpi-card p-0 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs uppercase tracking-widest text-slate-500 border-b border-slate-200">
            <tr>
              <th className="text-left py-3 px-4">N°</th>
              <th className="text-left py-3 px-4">Data</th>
              <th className="text-left py-3 px-4">Cliente</th>
              <th className="text-center py-3 px-4">DDT</th>
              <th className="text-right py-3 px-4">Imp.</th>
              <th className="text-right py-3 px-4">Totale</th>
              <th className="text-center py-3 px-4">Stato</th>
              <th className="text-right py-3 px-4">Azioni</th>
            </tr>
          </thead>
          <tbody>
            {list.map(f => (
              <tr key={f.id} className="border-b border-slate-100" data-testid={`fatt-${f.id}`}>
                <td className="py-2 px-4 font-mono font-bold">{f.numero}</td>
                <td className="py-2 px-4">{new Date(f.data).toLocaleDateString("it-IT")}</td>
                <td className="py-2 px-4">
                  <div>{docPrimary(f)}</div>
                  {docSecondary(f) && <div className="text-xs text-slate-500">{docSecondary(f)}</div>}
                </td>
                <td className="py-2 px-4 text-center text-xs text-slate-500">{f.ddt_numeri?.length || 0}</td>
                <td className="py-2 px-4 text-right font-mono">€ {f.imponibile.toFixed(2)}</td>
                <td className="py-2 px-4 text-right font-mono font-bold">€ {f.totale.toFixed(2)}</td>
                <td className="py-2 px-4 text-center">
                  {f.stato_incasso === "incassata" ? (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-emerald-100 text-emerald-700"><CheckCircle size={10} weight="fill" /> Incassata</span>
                  ) : (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-amber-100 text-amber-700">Da incassare</span>
                  )}
                </td>
                <td className="py-2 px-4 text-right space-x-1">
                  <Button variant="ghost" size="icon" onClick={() => openPdf(f)} title="Scarica PDF" data-testid={`fatt-pdf-${f.id}`}><FilePdf size={14} /></Button>
                  <Button variant="ghost" size="icon" onClick={() => validateXml(f)} title="Verifica conformità SdI" data-testid={`fatt-validate-${f.id}`}><ShieldCheck size={14} /></Button>
                  <Button variant="ghost" size="icon" onClick={() => downloadXmlPa(f)} title="Scarica XML Fattura Elettronica" data-testid={`fatt-xml-${f.id}`}><FileXls size={14} /></Button>
                  <Button variant="ghost" size="icon" onClick={() => openDetail(f)}><Eye size={14} /></Button>
                  {f.stato_incasso !== "incassata" && (
                    <Button size="sm" onClick={() => incassa(f)} className="bg-emerald-600 hover:bg-emerald-700" data-testid={`fatt-incassa-${f.id}`}>
                      <CurrencyEur size={12} className="mr-1" />Incassa
                    </Button>
                  )}
                  {f.stato_incasso !== "incassata" && (
                    <Button variant="ghost" size="icon" onClick={() => delFattura(f)} className="text-red-600"><Trash size={14} /></Button>
                  )}
                </td>
              </tr>
            ))}
            {list.length === 0 && <tr><td colSpan="8" className="text-center py-12 text-slate-400">Nessuna fattura</td></tr>}
          </tbody>
        </table>
      </div>

      {/* New fattura */}
      <Dialog open={genOpen} onOpenChange={setGenOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader><DialogTitle>Nuova fattura da DDT</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-3">
              <div className="col-span-2">
                <Label>Cliente *</Label>
                <Select value={genCli} onValueChange={setGenCli}>
                  <SelectTrigger data-testid="fatt-cliente"><SelectValue placeholder="Seleziona cliente…" /></SelectTrigger>
                  <SelectContent>
                    {clienti.filter(c => c.attivo !== false).map(c => <SelectItem key={c.id} value={c.id}>{clientePrimary(c)}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>IVA %</Label>
                <Input type="number" step="1" value={ivaPct} onChange={e => setIvaPct(e.target.value)} data-testid="fatt-iva" />
              </div>
            </div>

            {genCli && (
              <div>
                <Label className="mb-2 block">DDT fatturabili ({genDdts.length})</Label>
                {genDdts.length === 0 ? (
                  <div className="text-center text-sm text-slate-400 py-6 border border-dashed border-slate-200 rounded">Nessun DDT da fatturare per questo cliente</div>
                ) : (
                  <div className="border border-slate-200 rounded max-h-64 overflow-y-auto">
                    {genDdts.map(d => (
                      <label key={d.id} className="flex items-center gap-3 p-3 border-b border-slate-100 last:border-0 cursor-pointer hover:bg-slate-50" data-testid={`fatt-ddt-${d.id}`}>
                        <input type="checkbox" checked={genSelected.has(d.id)} onChange={() => toggleDdt(d.id)} className="rounded" />
                        <div className="flex-1">
                          <div className="font-mono text-sm font-bold">{d.numero}</div>
                          <div className="text-xs text-slate-500">{new Date(d.data).toLocaleDateString("it-IT")} • {d.righe.length} righe</div>
                        </div>
                        <div className="font-mono font-bold">€ {d.imponibile.toFixed(2)}</div>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div>
              <Label>Scadenza (opzionale)</Label>
              <Input type="date" value={scadenza} onChange={e => setScadenza(e.target.value)} />
            </div>

            {genSelected.size > 0 && (
              <div className="bg-indaco/5 rounded p-3 space-y-1 text-sm">
                <div className="flex justify-between"><span>Imponibile ({genSelected.size} DDT)</span><span className="font-mono">€ {imponibileSel.toFixed(2)}</span></div>
                <div className="flex justify-between text-slate-600"><span>IVA {ivaPct}%</span><span className="font-mono">€ {ivaSel.toFixed(2)}</span></div>
                <div className="flex justify-between text-lg font-bold border-t border-indaco/20 pt-2"><span>Totale</span><span className="font-mono text-indaco">€ {totaleSel.toFixed(2)}</span></div>
              </div>
            )}

            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setGenOpen(false)}>Annulla</Button>
              <Button onClick={generate} disabled={genSelected.size === 0} className="bg-indaco hover:bg-indaco-dark" data-testid="gen-fatt-btn">
                <Receipt size={14} className="mr-1" />Genera fattura
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Detail */}
      <Dialog open={!!detail} onOpenChange={(o) => { if (!o) setDetail(null); }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>Fattura {detail?.numero}</DialogTitle></DialogHeader>
          {detail && (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-2">
                <div><div className="overline">Cliente</div>
                  <div className="font-semibold">{detail.cliente_nome}</div>
                  {detail.cliente_denominazione && <div className="text-xs text-slate-500">{detail.cliente_denominazione}</div>}
                </div>
                <div><div className="overline">Stato</div><div className={`font-semibold ${detail.stato_incasso === "incassata" ? "text-emerald-600" : "text-amber-600"}`}>{detail.stato_incasso}</div></div>
              </div>
              <div>
                <div className="overline mb-1">DDT inclusi</div>
                <div className="space-y-1">
                  {(detail.ddts || []).map(d => (
                    <div key={d.id} className="flex justify-between text-xs font-mono py-1 border-b border-slate-100">
                      <span>{d.numero}</span>
                      <span>€ {d.imponibile.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="border-t border-slate-200 pt-3 space-y-1">
                <div className="flex justify-between"><span>Imponibile</span><span className="font-mono">€ {detail.imponibile.toFixed(2)}</span></div>
                <div className="flex justify-between text-slate-500"><span>IVA {detail.iva_pct}%</span><span className="font-mono">€ {detail.iva.toFixed(2)}</span></div>
                <div className="flex justify-between font-bold text-lg"><span>Totale</span><span className="font-mono text-indaco">€ {detail.totale.toFixed(2)}</span></div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}


/* ------------------------------------------------------------------ */
/*  Bulk XML export — mese o intervallo                                */
/* ------------------------------------------------------------------ */

const MESI = ["Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno",
              "Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"];

function BulkXmlExport() {
  const today = new Date();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState("month"); // "month" | "range"
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [count, setCount] = useState(null);
  const [downloading, setDownloading] = useState(false);

  // Date range for the current selection
  const computeRange = useCallback(() => {
    if (mode === "month") {
      const m = String(month).padStart(2, "0");
      const last = new Date(year, month, 0).getDate();
      return { from: `${year}-${m}-01`, to: `${year}-${m}-${String(last).padStart(2, "0")}` };
    }
    return { from: fromDate, to: toDate };
  }, [mode, year, month, fromDate, toDate]);

  // Refresh count whenever selection changes
  useEffect(() => {
    if (!open) return;
    const { from, to } = computeRange();
    if (!from || !to) { setCount(null); return; }
    let cancelled = false;
    api.get("/fatture", { params: { stato_incasso: undefined } })
      .then(({ data }) => {
        if (cancelled) return;
        const c = (data || []).filter(f => {
          const d = (f.data || "").slice(0, 10);
          return d >= from && d <= to;
        }).length;
        setCount(c);
      })
      .catch(() => { if (!cancelled) setCount(null); });
    return () => { cancelled = true; };
  }, [open, computeRange]);

  const download = async () => {
    const { from, to } = computeRange();
    if (mode === "range" && (!from || !to)) { toast.error("Seleziona Da e A"); return; }
    if (from > to) { toast.error("La data 'Da' deve essere precedente a 'A'"); return; }
    setDownloading(true);
    try {
      const params = mode === "month"
        ? { month: `${year}-${String(month).padStart(2, "0")}` }
        : { from, to };
      const res = await api.get("/fatture/xml-bulk", { params, responseType: "blob" });
      const disp = res.headers["content-disposition"] || "";
      const m = disp.match(/filename="?([^";]+)"?/);
      const filename = m ? m[1] : "Fatture_Elettroniche.zip";
      const total = res.headers["x-export-total"];
      const included = res.headers["x-export-included"];
      const skipped = res.headers["x-export-skipped"];
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = filename; a.click();
      URL.revokeObjectURL(url);
      toast.success(`ZIP scaricato · ${included}/${total} XML${skipped > 0 ? ` (${skipped} saltate)` : ""}`);
      setOpen(false);
    } catch (e) {
      let msg = "Errore generazione ZIP";
      if (e.response?.data instanceof Blob) {
        try { const t = await e.response.data.text(); msg = JSON.parse(t).detail || msg; } catch { /* ignore */ }
      } else if (e.response?.data?.detail) { msg = e.response.data.detail; }
      toast.error(msg);
    } finally { setDownloading(false); }
  };

  const years = [];
  for (let y = today.getFullYear(); y >= today.getFullYear() - 4; y--) years.push(y);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" className="border-indaco/30 text-indaco hover:bg-indaco/5" data-testid="bulk-xml-btn">
          <Package size={16} weight="duotone" className="mr-1.5" />
          Esporta XML del periodo
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-96 p-4" align="end" data-testid="bulk-xml-popover">
        <div className="space-y-3">
          <div>
            <div className="overline text-slate-400">Esportazione massiva</div>
            <h3 className="font-display font-bold text-base text-slate-900">XML Fatture Elettroniche</h3>
            <p className="text-xs text-slate-500 mt-0.5">Scarica un ZIP con tutti gli XML del periodo (uno per fattura) pronti per l'invio allo SdI.</p>
          </div>

          {/* Mode tabs */}
          <div className="flex bg-slate-100 rounded-md p-0.5">
            <button
              type="button"
              onClick={() => setMode("month")}
              className={`flex-1 px-3 py-1.5 text-xs font-medium rounded transition-colors ${mode === "month" ? "bg-white text-indaco shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
              data-testid="bulk-mode-month">
              Mese
            </button>
            <button
              type="button"
              onClick={() => setMode("range")}
              className={`flex-1 px-3 py-1.5 text-xs font-medium rounded transition-colors ${mode === "range" ? "bg-white text-indaco shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
              data-testid="bulk-mode-range">
              Intervallo date
            </button>
          </div>

          {mode === "month" ? (
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs">Mese</Label>
                <select
                  value={month}
                  onChange={(e) => setMonth(Number(e.target.value))}
                  data-testid="bulk-month-select"
                  className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm focus:outline-none focus:ring-2 focus:ring-indaco">
                  {MESI.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
                </select>
              </div>
              <div>
                <Label className="text-xs">Anno</Label>
                <select
                  value={year}
                  onChange={(e) => setYear(Number(e.target.value))}
                  data-testid="bulk-year-select"
                  className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm focus:outline-none focus:ring-2 focus:ring-indaco">
                  {years.map(y => <option key={y} value={y}>{y}</option>)}
                </select>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs">Da</Label>
                <Input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} className="h-9 text-xs" data-testid="bulk-from-date" />
              </div>
              <div>
                <Label className="text-xs">A</Label>
                <Input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} className="h-9 text-xs" data-testid="bulk-to-date" />
              </div>
            </div>
          )}

          {/* Live count */}
          <div className="rounded-md bg-slate-50 border border-slate-200 px-3 py-2 text-sm flex items-center gap-2" data-testid="bulk-count-pill">
            <CalendarBlank size={14} weight="duotone" className="text-indaco" />
            {count === null ? (
              <span className="text-slate-400 font-mono text-xs">caricamento…</span>
            ) : (
              <span>
                <b className="text-indaco">{count}</b>{" "}
                <span className="text-slate-600">{count === 1 ? "fattura" : "fatture"} nel periodo</span>
              </span>
            )}
          </div>

          <Button
            onClick={download}
            disabled={downloading || count === 0}
            className="w-full bg-indaco hover:bg-indaco-dark"
            data-testid="bulk-xml-download-btn">
            <Package size={14} weight="bold" className="mr-1.5" />
            {downloading ? "Generazione ZIP…" : "Scarica ZIP"}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
