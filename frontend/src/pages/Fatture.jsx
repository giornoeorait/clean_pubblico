import React, { useCallback, useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { Receipt, CheckCircle, Plus, Eye, Trash, CurrencyEur, FilePdf } from "@phosphor-icons/react";
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

  return (
    <div>
      <PageHeader
        eyebrow="Contabilità"
        title="Fatturazione"
        subtitle="Genera fatture riepilogative da DDT non fatturati. Gestisci incassi e sospesi."
        actions={
          <Button onClick={() => setGenOpen(true)} className="bg-indaco hover:bg-indaco-dark" data-testid="new-fattura-btn">
            <Plus size={16} className="mr-1" />Nuova fattura
          </Button>
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
                <td className="py-2 px-4">{f.cliente_nome}</td>
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
                    {clienti.filter(c => c.attivo !== false).map(c => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}
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
                <div><div className="overline">Cliente</div><div className="font-semibold">{detail.cliente_nome}</div></div>
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
