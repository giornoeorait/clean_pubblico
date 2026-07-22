import React, { useCallback, useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import ClienteCombobox from "../components/ClienteCombobox";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { Receipt, CheckCircle, Plus, Eye, Trash, CurrencyEur, FilePdf, FileXls, Package, CalendarBlank, ShieldCheck, PencilLine, PaperPlaneTilt, Envelope, Warning } from "@phosphor-icons/react";
import { Popover, PopoverContent, PopoverTrigger } from "../components/ui/popover";
import { docPrimary, docSecondary } from "../lib/clienteLabel";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";

export default function Fatture() {
  const { user } = useAuth() || {};
  const canRinumera = user?.role === "admin" || user?.role === "superadmin";
  const [list, setList] = useState([]);
  const [clienti, setClienti] = useState([]);
  const [filterStato, setFilterStato] = useState("all");
  const [filterDataInizio, setFilterDataInizio] = useState("");
  const [filterDataFine, setFilterDataFine] = useState("");
  const [filterPiva, setFilterPiva] = useState("");
  const [filterCliId, setFilterCliId] = useState("");
  const [totali, setTotali] = useState({ count: 0, totale_imponibile: 0, totale_iva: 0, totale_documento: 0 });

  // New fattura dialog
  const [genOpen, setGenOpen] = useState(false);
  const [genMode, setGenMode] = useState("cliente"); // "cliente" | "ragione_sociale"
  const [genCli, setGenCli] = useState("");
  const [genRS, setGenRS] = useState(""); // ragione sociale selezionata
  const [ragioniSociali, setRagioniSociali] = useState([]);
  const [genDdts, setGenDdts] = useState([]);
  const [genSelected, setGenSelected] = useState(new Set());
  const [ivaPct, setIvaPct] = useState(22);
  const [scadenza, setScadenza] = useState("");

  // Detail
  const [detail, setDetail] = useState(null);

  // Rinumerazione + Ridata
  const [renumTarget, setRenumTarget] = useState(null); // fattura selezionata
  const [renumNumero, setRenumNumero] = useState("");
  const [renumData, setRenumData] = useState("");
  const [renumMotivazione, setRenumMotivazione] = useState("");
  const [renumSaving, setRenumSaving] = useState(false);

  // Invio email
  const [emailTarget, setEmailTarget] = useState(null);
  const [emailTo, setEmailTo] = useState("");
  const [emailSending, setEmailSending] = useState(false);

  const fetchAll = useCallback(async () => {
    const params = {};
    if (filterStato !== "all") params.stato_incasso = filterStato;
    if (filterDataInizio) params.data_inizio = filterDataInizio;
    if (filterDataFine) params.data_fine = filterDataFine;
    if (filterPiva && filterPiva.trim()) params.piva = filterPiva.trim();
    if (filterCliId) params.cliente_id = filterCliId;
    const [f, c, rs, t] = await Promise.all([
      api.get(`/fatture`, { params }),
      api.get("/clienti"),
      api.get("/fatture/ragioni-sociali").catch(() => ({ data: [] })),
      api.get("/fatture/summary", { params }).catch(() => ({ data: { count: 0, totale_imponibile: 0, totale_iva: 0, totale_documento: 0 } })),
    ]);
    setList(f.data); setClienti(c.data); setRagioniSociali(rs.data || []); setTotali(t.data);
  }, [filterStato, filterDataInizio, filterDataFine, filterPiva, filterCliId]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const loadFatturabili = async (cliId) => {
    try {
      const { data } = await api.get(`/fatture/fatturabili?cliente_id=${cliId}`);
      setGenDdts(data.ddts);
      setGenSelected(new Set(data.ddts.map(d => d.id))); // select all by default
    } catch { setGenDdts([]); setGenSelected(new Set()); }
  };

  const loadFatturabiliRS = async (rs) => {
    try {
      const { data } = await api.get(`/fatture/fatturabili-rs?ragione_sociale=${encodeURIComponent(rs)}`);
      setGenDdts(data.ddts);
      setGenSelected(new Set(data.ddts.map(d => d.id)));
      // in RS mode il cliente intestatario è il primo dei siblings (denominazione più chiara)
      const first = (data.clienti || [])[0];
      if (first) setGenCli(first.id);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore caricamento");
      setGenDdts([]); setGenSelected(new Set());
    }
  };

  useEffect(() => {
    if (genMode === "cliente" && genCli) loadFatturabili(genCli);
    else if (genMode === "ragione_sociale" && genRS) loadFatturabiliRS(genRS);
    else { setGenDdts([]); setGenSelected(new Set()); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [genCli, genRS, genMode]);

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
      const payload = {
        cliente_id: genCli,
        ddt_ids: Array.from(genSelected),
        iva_pct: parseFloat(ivaPct),
        scadenza: scadenza || undefined,
      };
      if (genMode === "ragione_sociale") payload.ragione_sociale_mode = true;
      const { data } = await api.post("/fatture", payload);
      toast.success(`Fattura ${data.numero} generata — € ${data.totale.toFixed(2)}`);
      setGenOpen(false); setGenCli(""); setGenRS(""); setGenMode("cliente"); setScadenza(""); fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const openEmailDialog = (f) => {
    setEmailTarget(f);
    // pre-popola con l'email del cliente (fatturazione, o email base)
    const cli = clienti.find(c => c.id === f.cliente_id) || {};
    setEmailTo(cli.email_fatturazione || cli.email || cli.pec || "");
  };

  const submitEmail = async () => {
    if (!emailTarget) return;
    if (!emailTo || !emailTo.includes("@")) {
      toast.error("Inserisci un indirizzo e-mail valido");
      return;
    }
    setEmailSending(true);
    try {
      const { data } = await api.post(`/fatture/${emailTarget.id}/send-email`, { to: emailTo.trim() });
      if (data.status === "sent") toast.success(`E-mail inviata a ${data.to}`);
      else if (data.status === "logged") toast(`SMTP non configurato — registrata in log (destinatario: ${data.to})`, { icon: "ℹ️" });
      else toast.error(`Errore invio: ${data.error || "sconosciuto"}`);
      setEmailTarget(null); setEmailTo("");
      fetchAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore invio email");
    } finally {
      setEmailSending(false);
    }
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

  const openRenum = (f) => {
    if (f.xml_transmitted) {
      toast.error("Fattura trasmessa a SDI: dati fiscali immutabili per legge");
      return;
    }
    setRenumTarget(f);
    setRenumNumero(f.numero || "");
    // pre-popola data corrente della fattura (YYYY-MM-DD)
    const d = f.data ? new Date(f.data) : null;
    if (d && !isNaN(d)) {
      const yyyy = d.getFullYear();
      const mm = String(d.getMonth() + 1).padStart(2, "0");
      const dd = String(d.getDate()).padStart(2, "0");
      setRenumData(`${yyyy}-${mm}-${dd}`);
    } else {
      setRenumData("");
    }
    setRenumMotivazione("");
  };

  const closeRenum = () => {
    setRenumTarget(null);
    setRenumNumero("");
    setRenumData("");
    setRenumMotivazione("");
  };

  const submitRenum = async () => {
    if (!renumTarget) return;
    const nuovoNumero = (renumNumero || "").trim();
    const nuovaData = (renumData || "").trim();
    const motivazione = (renumMotivazione || "").trim();
    // Valida motivazione
    if (motivazione.length < 10) {
      toast.error("La motivazione è obbligatoria (min 10 caratteri) e verrà registrata nell'audit log");
      return;
    }
    // Valida che almeno un cambio sia stato fatto
    const origData = renumTarget.data ? new Date(renumTarget.data) : null;
    const origDataIso = origData && !isNaN(origData)
      ? `${origData.getFullYear()}-${String(origData.getMonth() + 1).padStart(2, "0")}-${String(origData.getDate()).padStart(2, "0")}`
      : "";
    const numeroDiverso = nuovoNumero && nuovoNumero !== renumTarget.numero;
    const dataDiversa = nuovaData && nuovaData !== origDataIso;
    if (!numeroDiverso && !dataDiversa) {
      toast.error("Modifica almeno il numero o la data prima di salvare");
      return;
    }
    setRenumSaving(true);
    try {
      const payload = { motivazione };
      if (numeroDiverso) payload.numero = nuovoNumero;
      if (dataDiversa) payload.nuova_data = nuovaData;
      const { data } = await api.patch(`/fatture/${renumTarget.id}/rinumera`, payload);
      const parts = [];
      if (numeroDiverso) parts.push(`num: ${data.numero}`);
      if (dataDiversa) parts.push(`data: ${new Date(data.data).toLocaleDateString("it-IT")}`);
      toast.success(`Fattura aggiornata (${parts.join(", ")})`);
      closeRenum();
      fetchAll();
    } catch (e) {
      const d = e.response?.data?.detail;
      const msg = typeof d === "string" ? d : (Array.isArray(d) ? d.map(x => x.msg).join("; ") : "Errore rinumerazione");
      toast.error(msg);
    } finally {
      setRenumSaving(false);
    }
  };

  const segnaTrasmessa = async (f) => {
    if (!window.confirm(`Confermi che la fattura ${f.numero} è stata inviata a SDI?\nDopo questa azione il numero sarà bloccato.`)) return;
    try {
      await api.post(`/fatture/${f.id}/segna-trasmessa`);
      toast.success(`${f.numero} · marcata come trasmessa a SDI`);
      fetchAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore");
    }
  };

  const sbloccaTrasmissione = async (f) => {
    if (!window.confirm(`ATTENZIONE: sbloccare la trasmissione a SDI di ${f.numero}?\nUsalo solo se è stato un errore. Riabiliterà la rinumerazione.`)) return;
    try {
      await api.post(`/fatture/${f.id}/annulla-trasmissione`);
      toast.success("Trasmissione SDI annullata");
      fetchAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore");
    }
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

      <div className="kpi-card p-4 mb-4">
        <div className="flex flex-wrap items-end gap-3">
          {/* Stato */}
          <div className="flex gap-1">
            {[["all", "Tutte"], ["da_incassare", "Da incassare"], ["incassata", "Incassate"]].map(([k, l]) => (
              <button
                key={k}
                onClick={() => setFilterStato(k)}
                className={`px-3 py-1.5 text-xs font-semibold rounded-md ${filterStato === k ? "bg-indaco text-white" : "bg-white border border-slate-200 text-slate-600"}`}
                data-testid={`fatt-filter-${k}`}
              >{l}</button>
            ))}
          </div>

          {/* Range date */}
          <div>
            <Label className="text-[11px] text-slate-500 uppercase tracking-wide">Data dal</Label>
            <Input
              type="date"
              value={filterDataInizio}
              onChange={(e) => setFilterDataInizio(e.target.value)}
              className="h-9 w-40"
              data-testid="fatt-filter-data-inizio"
            />
          </div>
          <div>
            <Label className="text-[11px] text-slate-500 uppercase tracking-wide">Data al</Label>
            <Input
              type="date"
              value={filterDataFine}
              onChange={(e) => setFilterDataFine(e.target.value)}
              className="h-9 w-40"
              data-testid="fatt-filter-data-fine"
            />
          </div>

          {/* Cliente */}
          <div className="min-w-[220px] flex-1">
            <Label className="text-[11px] text-slate-500 uppercase tracking-wide">Cliente</Label>
            <ClienteCombobox
              value={filterCliId || "all"}
              onChange={(v) => setFilterCliId(v === "all" ? "" : v)}
              clienti={clienti}
              allowAll
              allLabel="Tutti i clienti"
              testId="fatt-filter-cliente"
            />
          </div>

          {/* PIVA */}
          <div>
            <Label className="text-[11px] text-slate-500 uppercase tracking-wide">P.IVA / CF</Label>
            <Input
              value={filterPiva}
              onChange={(e) => setFilterPiva(e.target.value)}
              placeholder="es. 01234567890"
              className="h-9 w-44 font-mono"
              data-testid="fatt-filter-piva"
            />
          </div>

          {/* Reset */}
          {(filterDataInizio || filterDataFine || filterPiva || filterCliId || filterStato !== "all") && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => { setFilterStato("all"); setFilterDataInizio(""); setFilterDataFine(""); setFilterPiva(""); setFilterCliId(""); }}
              data-testid="fatt-filter-reset"
            >Azzera filtri</Button>
          )}
        </div>
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
                <td className="py-2 px-4 font-mono font-bold">
                  {f.numero}
                  <div className="flex items-center gap-1 mt-0.5">
                    {f.xml_transmitted && (
                      <div title={`Trasmessa a SDI${f.xml_transmitted_at ? ` il ${new Date(f.xml_transmitted_at).toLocaleDateString("it-IT")}` : ""}`} className="text-[9px] uppercase tracking-widest text-emerald-700 font-semibold flex items-center gap-0.5">
                        <PaperPlaneTilt size={9} weight="fill" /> SDI
                      </div>
                    )}
                    {f.email_last_status === "sent" && (
                      <div title={`E-mail inviata${f.email_last_at ? ` il ${new Date(f.email_last_at).toLocaleString("it-IT")}` : ""} a ${f.email_last_to || ""}`} className="text-[9px] uppercase tracking-widest text-emerald-700 font-semibold flex items-center gap-0.5" data-testid={`email-badge-sent-${f.id}`}>
                        <Envelope size={9} weight="fill" /> inviata
                      </div>
                    )}
                    {f.email_last_status === "failed" && (
                      <div title="Ultimo invio fallito" className="text-[9px] uppercase tracking-widest text-red-600 font-semibold flex items-center gap-0.5" data-testid={`email-badge-failed-${f.id}`}>
                        <Warning size={9} weight="fill" /> errore
                      </div>
                    )}
                    {f.email_last_status === "logged" && (
                      <div title="SMTP non configurato: solo log" className="text-[9px] uppercase tracking-widest text-slate-500 font-semibold flex items-center gap-0.5" data-testid={`email-badge-logged-${f.id}`}>
                        <Envelope size={9} /> log
                      </div>
                    )}
                  </div>
                </td>
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
                  <Button variant="ghost" size="icon" onClick={() => openEmailDialog(f)} title="Invia via email" data-testid={`fatt-email-${f.id}`}><Envelope size={14} /></Button>
                  <Button variant="ghost" size="icon" onClick={() => openDetail(f)} title="Dettaglio" data-testid={`fatt-detail-${f.id}`}><Eye size={14} /></Button>
                  {!f.xml_transmitted && canRinumera && (
                    <Button variant="ghost" size="icon" onClick={() => openRenum(f)} title="Rinumera e ridata fattura" data-testid={`fatt-renum-${f.id}`}><PencilLine size={14} /></Button>
                  )}
                  {!f.xml_transmitted ? (
                    <Button variant="ghost" size="icon" onClick={() => segnaTrasmessa(f)} title="Segna come trasmessa a SDI (blocca il numero)" data-testid={`fatt-segna-sdi-${f.id}`}><PaperPlaneTilt size={14} className="text-indaco" /></Button>
                  ) : (
                    <Button variant="ghost" size="icon" onClick={() => sbloccaTrasmissione(f)} title="Sblocca trasmissione SDI (solo admin, per errori)" data-testid={`fatt-sblocca-sdi-${f.id}`}><PaperPlaneTilt size={14} weight="fill" className="text-emerald-600" /></Button>
                  )}
                  {f.stato_incasso !== "incassata" && (
                    <Button size="sm" onClick={() => incassa(f)} className="bg-emerald-600 hover:bg-emerald-700" data-testid={`fatt-incassa-${f.id}`}>
                      <CurrencyEur size={12} className="mr-1" />Incassa
                    </Button>
                  )}
                  {f.stato_incasso !== "incassata" && !f.xml_transmitted && (
                    <Button variant="ghost" size="icon" onClick={() => delFattura(f)} className="text-red-600" title="Elimina" data-testid={`fatt-del-${f.id}`}><Trash size={14} /></Button>
                  )}
                </td>
              </tr>
            ))}
            {list.length === 0 && <tr><td colSpan="8" className="text-center py-12 text-slate-400">Nessuna fattura</td></tr>}
          </tbody>
          {totali.count > 0 && (
            <tfoot className="border-t-2 border-slate-300 bg-slate-50" data-testid="fatt-totali-row">
              <tr>
                <td className="py-3 px-4 font-semibold text-slate-700 uppercase text-xs tracking-widest" colSpan={3}>
                  Totali · {totali.count} fatture
                </td>
                <td className="py-3 px-4"></td>
                <td className="py-3 px-4 text-right font-mono font-bold text-slate-800" data-testid="fatt-tot-imponibile">
                  € {totali.totale_imponibile.toFixed(2)}
                </td>
                <td className="py-3 px-4 text-right font-mono font-bold text-indaco text-base" data-testid="fatt-tot-documento">
                  € {totali.totale_documento.toFixed(2)}
                </td>
                <td className="py-3 px-4 text-center text-[11px] text-slate-500">
                  <div>IVA</div>
                  <div className="font-mono font-semibold text-slate-700" data-testid="fatt-tot-iva">€ {totali.totale_iva.toFixed(2)}</div>
                </td>
                <td className="py-3 px-4"></td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      {/* New fattura */}
      <Dialog open={genOpen} onOpenChange={setGenOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader><DialogTitle>Nuova fattura da DDT</DialogTitle></DialogHeader>
          <div className="space-y-4">
            {/* Modalità: per Cliente o per Ragione Sociale */}
            <div className="flex gap-2 border-b border-slate-200 pb-2">
              <button
                type="button"
                onClick={() => { setGenMode("cliente"); setGenRS(""); }}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition ${genMode === "cliente" ? "bg-indaco text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
                data-testid="fatt-mode-cliente"
              >
                Fattura per Cliente
              </button>
              <button
                type="button"
                onClick={() => { setGenMode("ragione_sociale"); setGenCli(""); }}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition ${genMode === "ragione_sociale" ? "bg-indaco text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
                data-testid="fatt-mode-rs"
              >
                Fattura per Ragione Sociale
              </button>
              <div className="ml-auto text-[11px] text-slate-500 self-center max-w-xs text-right">
                {genMode === "ragione_sociale" && "Raggruppa i DDT di tutti i clienti che condividono la stessa Ragione Sociale."}
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              {genMode === "cliente" ? (
                <div className="col-span-2">
                  <Label>Cliente *</Label>
                  <ClienteCombobox
                    clienti={clienti.filter(c => c.attivo !== false)}
                    value={genCli}
                    onChange={setGenCli}
                    testId="fatt-cliente"
                  />
                </div>
              ) : (
                <div className="col-span-2">
                  <Label>Ragione Sociale *</Label>
                  <select
                    value={genRS}
                    onChange={(e) => setGenRS(e.target.value)}
                    className="w-full h-10 px-3 rounded-md border border-slate-200 bg-white text-sm"
                    data-testid="fatt-rs-select"
                  >
                    <option value="">Seleziona ragione sociale…</option>
                    {ragioniSociali.map(rs => (
                      <option key={rs.ragione_sociale} value={rs.ragione_sociale}>
                        {rs.ragione_sociale} · {rs.clienti_count} clienti
                      </option>
                    ))}
                  </select>
                  {ragioniSociali.length === 0 && (
                    <div className="text-[11px] text-amber-700 mt-1">
                      Nessuna Ragione Sociale con 2+ clienti trovata. Le RS con un solo cliente equivalgono alla fattura per cliente.
                    </div>
                  )}
                </div>
              )}
              <div>
                <Label>IVA %</Label>
                <Input type="number" step="1" value={ivaPct} onChange={e => setIvaPct(e.target.value)} data-testid="fatt-iva" />
                <div className="text-[10px] text-slate-500 mt-0.5">Suffisso: <b>{Number(ivaPct) === 0 ? "C" : "F"}</b></div>
              </div>
            </div>

            {(genCli || genRS) && (
              <div>
                <Label className="mb-2 block">DDT fatturabili ({genDdts.length})</Label>
                {genDdts.length === 0 ? (
                  <div className="text-center text-sm text-slate-400 py-6 border border-dashed border-slate-200 rounded">
                    {genMode === "ragione_sociale" ? "Nessun DDT da fatturare per questa Ragione Sociale" : "Nessun DDT da fatturare per questo cliente"}
                  </div>
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
                <div className="overline mb-1">DDT inclusi ({(detail.ddt_dettagli || detail.ddts || []).length})</div>
                <div className="space-y-1 max-h-48 overflow-y-auto" data-testid="fatt-detail-ddt">
                  {(detail.ddt_dettagli || detail.ddts || []).map(d => (
                    <div key={d.id || d.numero} className="flex items-center justify-between text-xs py-1 border-b border-slate-100">
                      <div>
                        <span className="font-mono font-bold">{d.numero}</span>
                        {d.data && <span className="text-slate-500 ml-2">{new Date(d.data).toLocaleDateString("it-IT")}</span>}
                      </div>
                      <span className="font-mono">€ {Number(d.imponibile || 0).toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              </div>
              {detail.riepilogo_articoli && detail.riepilogo_articoli.length > 0 && (
                <div>
                  <div className="overline mb-1">Riepilogo cumulativo articoli</div>
                  <div className="rounded border border-slate-200 overflow-hidden" data-testid="fatt-detail-riepilogo">
                    <table className="w-full text-xs">
                      <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider text-[10px]">
                        <tr>
                          <th className="text-left px-2 py-1.5">Articolo</th>
                          <th className="text-center px-2 py-1.5">Q.tà tot.</th>
                          <th className="text-right px-2 py-1.5">Prezzo unit.</th>
                          <th className="text-right px-2 py-1.5">Totale</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.riepilogo_articoli.map((r, i) => (
                          <tr key={r.articolo_id || i} className="border-t border-slate-100">
                            <td className="px-2 py-1.5">
                              <div className="font-medium">{r.descrizione}</div>
                              {r.codice && <div className="font-mono text-[10px] text-slate-500">{r.codice}</div>}
                            </td>
                            <td className="px-2 py-1.5 text-center font-mono font-bold">
                              {r.quantita_totale} <span className="text-slate-400">{r.unita_misura}</span>
                            </td>
                            <td className="px-2 py-1.5 text-right font-mono text-slate-600">€ {Number(r.prezzo_unitario_medio).toFixed(4)}</td>
                            <td className="px-2 py-1.5 text-right font-mono font-semibold text-indaco">€ {Number(r.totale).toFixed(2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
              <div className="border-t border-slate-200 pt-3 space-y-1">
                <div className="flex justify-between"><span>Imponibile</span><span className="font-mono">€ {detail.imponibile.toFixed(2)}</span></div>
                <div className="flex justify-between text-slate-500"><span>IVA {detail.iva_pct}%</span><span className="font-mono">€ {detail.iva.toFixed(2)}</span></div>
                <div className="flex justify-between font-bold text-lg"><span>Totale</span><span className="font-mono text-indaco">€ {detail.totale.toFixed(2)}</span></div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Dialog invio email */}
      <Dialog open={!!emailTarget} onOpenChange={(o) => { if (!o) { setEmailTarget(null); setEmailTo(""); } }}>
        <DialogContent className="max-w-md" data-testid="fatt-email-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Envelope size={18} /> Invia fattura via email</DialogTitle>
          </DialogHeader>
          {emailTarget && (
            <div className="space-y-3">
              <div className="text-sm">
                <div className="text-slate-500">Fattura</div>
                <div className="font-mono font-bold text-base">{emailTarget.numero}</div>
              </div>
              <div>
                <Label>Destinatario</Label>
                <Input
                  type="email"
                  value={emailTo}
                  onChange={(e) => setEmailTo(e.target.value)}
                  placeholder="cliente@example.com"
                  data-testid="fatt-email-to"
                />
                <div className="text-[11px] text-slate-500 mt-1">
                  Prepopolato dall&apos;email del cliente (fatturazione / principale / PEC).
                </div>
              </div>
              <div className="rounded bg-slate-50 border border-slate-200 px-3 py-2 text-[11px] text-slate-600">
                <div><b>Oggetto:</b> Fattura n. {emailTarget.numero} del {new Date(emailTarget.data).toLocaleDateString("it-IT")}</div>
                <div className="mt-2 text-slate-500 italic">
                  Gentile Cliente, come da riferimenti in oggetto, inviamo in allegato copia cortesia della fattura relativa ai servizi mensili erogati. Cordiali saluti.
                </div>
                <div className="mt-2 text-[10px] text-slate-500">Il PDF della fattura viene generato e allegato automaticamente.</div>
              </div>
              <div className="flex justify-end gap-2 pt-2 border-t border-slate-200">
                <Button variant="outline" onClick={() => { setEmailTarget(null); setEmailTo(""); }}>Annulla</Button>
                <Button className="bg-indaco hover:bg-indaco-dark" onClick={submitEmail} disabled={emailSending} data-testid="fatt-email-send">
                  {emailSending ? "Invio…" : "Invia"}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Dialog Rinumera e Ridata fattura */}
      <Dialog open={!!renumTarget} onOpenChange={(o) => { if (!o) closeRenum(); }}>
        <DialogContent className="max-w-lg" data-testid="fatt-renum-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <PencilLine size={18} /> Rinumera e ridata fattura
            </DialogTitle>
          </DialogHeader>
          {renumTarget && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <div className="text-slate-500 text-[11px] uppercase tracking-wide">Numero attuale</div>
                  <div className="font-mono font-bold text-base">{renumTarget.numero}</div>
                </div>
                <div>
                  <div className="text-slate-500 text-[11px] uppercase tracking-wide">Data attuale</div>
                  <div className="font-mono font-bold text-base">{new Date(renumTarget.data).toLocaleDateString("it-IT")}</div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Nuovo numero</Label>
                  <Input
                    value={renumNumero}
                    onChange={(e) => setRenumNumero(e.target.value.toUpperCase())}
                    placeholder="es. FT-2026-00042F"
                    className="font-mono"
                    data-testid="fatt-renum-input"
                  />
                  <div className="text-[10px] text-slate-500 mt-1">Formato: <code>FT-YYYY-NNNNN[F/C]</code></div>
                </div>
                <div>
                  <Label>Nuova data</Label>
                  <Input
                    type="date"
                    value={renumData}
                    onChange={(e) => setRenumData(e.target.value)}
                    data-testid="fatt-renum-data"
                  />
                  <div className="text-[10px] text-slate-500 mt-1">L&apos;anno del numero deve coincidere con l&apos;anno della data.</div>
                </div>
              </div>
              <div>
                <Label>
                  Motivazione <span className="text-red-600">*</span>
                  <span className="text-[10px] text-slate-500 ml-2 normal-case">(obbligatoria — registrata in audit log non alterabile)</span>
                </Label>
                <textarea
                  value={renumMotivazione}
                  onChange={(e) => setRenumMotivazione(e.target.value)}
                  placeholder="es. Correzione errore materiale in fase di emissione (min. 10 caratteri)"
                  rows={3}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indaco/20 focus:border-indaco"
                  data-testid="fatt-renum-motivazione"
                />
                <div className={`text-[10px] mt-1 ${renumMotivazione.trim().length < 10 ? "text-red-600" : "text-emerald-700"}`}>
                  {renumMotivazione.trim().length}/10 caratteri minimi
                </div>
              </div>
              <div className="rounded-md bg-amber-50 border border-amber-200 px-3 py-2 text-[12px] text-amber-800">
                <b>Attenzione:</b> puoi modificare numero e/o data <b>solo se la fattura NON è stata trasmessa a SDI</b>.
                La modifica verrà registrata nell&apos;audit log con la tua motivazione, utente e timestamp.
              </div>
              <div className="flex justify-end gap-2 pt-2 border-t border-slate-200">
                <Button variant="outline" onClick={closeRenum} disabled={renumSaving}>Annulla</Button>
                <Button
                  className="bg-indaco hover:bg-indaco-dark"
                  onClick={submitRenum}
                  disabled={renumSaving || renumMotivazione.trim().length < 10}
                  data-testid="fatt-renum-save"
                >
                  {renumSaving ? "Salvataggio…" : "Rinumera e ridata"}
                </Button>
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
            <p className="text-xs text-slate-500 mt-0.5">Scarica un ZIP con tutti gli XML del periodo (uno per fattura) pronti per l&apos;invio allo SdI.</p>
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
