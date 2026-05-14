import React, { useCallback, useEffect, useMemo, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Plus, Trash, Receipt, Truck, CheckCircle, XCircle, FloppyDisk, FilePdf, PencilSimple } from "@phosphor-icons/react";
import { clientePrimary, clienteSecondary, docPrimary, docSecondary } from "../lib/clienteLabel";
import { toast } from "sonner";

export default function DDT() {
  const [list, setList] = useState([]);
  const [clienti, setClienti] = useState([]);
  const [articoli, setArticoli] = useState([]);
  const [filterCliente, setFilterCliente] = useState("all");
  const [filterStato, setFilterStato] = useState("all");
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [cliId, setCliId] = useState("");
  const [rows, setRows] = useState([]);
  const [note, setNote] = useState("");

  const fetchAll = useCallback(async () => {
    const params = [];
    if (filterCliente !== "all") params.push(`cliente_id=${filterCliente}`);
    if (filterStato !== "all") params.push(`stato_fatturazione=${filterStato}`);
    const q = params.length ? `?${params.join("&")}` : "";
    const [d, c, a] = await Promise.all([
      api.get(`/ddt${q}`),
      api.get("/clienti"),
      api.get("/articoli"),
    ]);
    setList(d.data); setClienti(c.data); setArticoli(a.data);
  }, [filterCliente, filterStato]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const selectedCliente = useMemo(() => clienti.find(c => c.id === cliId), [clienti, cliId]);

  const addRow = () => setRows(r => [...r, { articolo_id: "", quantita: 1 }]);
  const removeRow = (i) => setRows(r => r.filter((_, idx) => idx !== i));
  const updateRow = (i, field, v) => setRows(r => r.map((x, idx) => idx === i ? { ...x, [field]: v } : x));

  const resetForm = () => { setCliId(""); setRows([]); setNote(""); setEditingId(null); };

  const openEdit = (d) => {
    setEditingId(d.id);
    setCliId(d.cliente_id);
    setRows((d.righe || []).map(r => ({ articolo_id: r.articolo_id, quantita: r.quantita })));
    setNote(d.note || "");
    setFormOpen(true);
  };

  const openPdf = async (d) => {
    try {
      const res = await api.get(`/ddt/${d.id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      window.open(url, "_blank");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore PDF");
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!cliId) { toast.error("Seleziona un cliente"); return; }
    if (rows.length === 0) { toast.error("Aggiungi almeno una riga"); return; }
    const bad = rows.find(r => !r.articolo_id || !r.quantita || parseInt(r.quantita) <= 0);
    if (bad) { toast.error("Ogni riga deve avere articolo e quantità > 0"); return; }
    try {
      const payload = {
        cliente_id: cliId,
        note,
        righe: rows.map(r => ({ articolo_id: r.articolo_id, quantita: parseInt(r.quantita) || 0 })),
      };
      if (editingId) {
        await api.patch(`/ddt/${editingId}`, { note: payload.note, righe: payload.righe });
        toast.success("DDT aggiornato");
      } else {
        const { data } = await api.post("/ddt", payload);
        toast.success(`DDT ${data.numero} creato — totale €${data.imponibile.toFixed(2)}`);
      }
      setFormOpen(false); resetForm(); fetchAll();
    } catch (e2) { toast.error(e2.response?.data?.detail || "Errore"); }
  };

  const delDDT = async (d) => {
    if (!window.confirm(`Eliminare DDT ${d.numero}?`)) return;
    try {
      const { data } = await api.delete(`/ddt/${d.id}`);
      if (data?.reverted_ordinativo) {
        toast.success(`DDT eliminato · ${data.reverted_ordinativo} torna editabile`);
      } else {
        toast.success("Eliminato");
      }
      fetchAll();
    }
    catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const totaleList = list.reduce((s, d) => s + (d.imponibile || 0), 0);

  return (
    <div>
      <PageHeader
        eyebrow="Operativo"
        title="Documenti di Trasporto (D.D.T.)"
        subtitle="Crea DDT selezionando cliente e articoli — i prezzi vengono applicati automaticamente dal listino del cliente."
        actions={
          <Dialog open={formOpen} onOpenChange={(o) => { setFormOpen(o); if (!o) resetForm(); }}>
            <DialogTrigger asChild>
              <Button className="bg-indaco hover:bg-indaco-dark" data-testid="new-ddt-btn">
                <Plus size={16} className="mr-1" />Nuovo D.D.T.
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-3xl">
              <DialogHeader><DialogTitle>{editingId ? "Modifica D.D.T." : "Nuovo D.D.T."}</DialogTitle></DialogHeader>
              <form onSubmit={submit} className="space-y-4">
                <div>
                  <Label>Cliente *</Label>
                  <Select value={cliId} onValueChange={setCliId} disabled={!!editingId}>
                    <SelectTrigger data-testid="ddt-cliente"><SelectValue placeholder="Seleziona cliente…" /></SelectTrigger>
                    <SelectContent>
                      {clienti.filter(c => c.attivo !== false).map(c => (
                        <SelectItem key={c.id} value={c.id}>
                          <span className="font-medium">{clientePrimary(c)}</span>
                          {clienteSecondary(c) && <span className="text-slate-500"> · {clienteSecondary(c)}</span>}
                          {c.listino_id ? " • listino ✓" : " • no listino"}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {selectedCliente && !selectedCliente.listino_id && (
                    <p className="text-xs text-amber-700 mt-1">⚠ Il cliente non ha un listino associato — verrà usato il prezzo default dell'articolo.</p>
                  )}
                </div>

                <div>
                  <div className="flex items-center justify-between mb-2">
                    <Label>Righe DDT</Label>
                    <Button type="button" variant="outline" size="sm" onClick={addRow} data-testid="ddt-add-row"><Plus size={12} className="mr-1" />Aggiungi</Button>
                  </div>
                  {rows.length === 0 && <div className="text-center text-sm text-slate-400 py-4 border border-dashed border-slate-200 rounded">Aggiungi una riga</div>}
                  <div className="space-y-2">
                    {rows.map((r, i) => (
                      <div key={i} className="flex items-center gap-2" data-testid={`ddt-row-${i}`}>
                        <Select value={r.articolo_id} onValueChange={v => updateRow(i, "articolo_id", v)}>
                          <SelectTrigger className="flex-1"><SelectValue placeholder="Articolo…" /></SelectTrigger>
                          <SelectContent>
                            {articoli.map(a => <SelectItem key={a.id} value={a.id}>{a.codice} — {a.descrizione}</SelectItem>)}
                          </SelectContent>
                        </Select>
                        <Input type="number" step="1" min="1" className="w-24" placeholder="Qta" value={r.quantita} onChange={e => updateRow(i, "quantita", parseInt(e.target.value) || 0)} />
                        <Button type="button" variant="outline" size="icon" onClick={() => removeRow(i)}><Trash size={14} /></Button>
                      </div>
                    ))}
                  </div>
                </div>

                <div><Label>Note</Label><Textarea rows={2} value={note} onChange={e => setNote(e.target.value)} /></div>

                <div className="flex justify-end gap-2">
                  <Button type="button" variant="outline" onClick={() => setFormOpen(false)}>Annulla</Button>
                  <Button type="submit" className="bg-indaco hover:bg-indaco-dark" data-testid="save-ddt-btn"><FloppyDisk size={14} className="mr-1" />{editingId ? "Aggiorna DDT" : "Crea DDT"}</Button>
                </div>
              </form>
            </DialogContent>
          </Dialog>
        }
      />

      {/* Filtri */}
      <div className="flex flex-wrap gap-2 mb-4 items-end">
        <div>
          <Label className="text-xs">Cliente</Label>
          <Select value={filterCliente} onValueChange={setFilterCliente}>
            <SelectTrigger className="w-64"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tutti</SelectItem>
              {clienti.map(c => <SelectItem key={c.id} value={c.id}>{clientePrimary(c)}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs">Stato</Label>
          <Select value={filterStato} onValueChange={setFilterStato}>
            <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tutti</SelectItem>
              <SelectItem value="non_fatturato">Non fatturati</SelectItem>
              <SelectItem value="fatturato">Fatturati</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="ml-auto text-right">
          <div className="overline">Totale DDT visualizzati</div>
          <div className="font-display text-2xl font-bold text-indaco" data-testid="ddt-totale">€ {totaleList.toFixed(2)}</div>
        </div>
      </div>

      <div className="kpi-card p-0 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs uppercase tracking-widest text-slate-500 border-b border-slate-200">
            <tr>
              <th className="text-left py-3 px-4">N°</th>
              <th className="text-left py-3 px-4">Data</th>
              <th className="text-left py-3 px-4">Cliente</th>
              <th className="text-center py-3 px-4">Righe</th>
              <th className="text-right py-3 px-4">Imponibile</th>
              <th className="text-center py-3 px-4">Stato</th>
              <th className="text-right py-3 px-4">Azioni</th>
            </tr>
          </thead>
          <tbody>
            {list.map(d => (
              <tr key={d.id} className="border-b border-slate-100" data-testid={`ddt-${d.id}`}>
                <td className="py-2 px-4 font-mono font-bold">{d.numero}</td>
                <td className="py-2 px-4">{new Date(d.data).toLocaleDateString("it-IT")}</td>
                <td className="py-2 px-4">
                  <div>{docPrimary(d)}</div>
                  {docSecondary(d) && <div className="text-xs text-slate-500">{docSecondary(d)}</div>}
                </td>
                <td className="py-2 px-4 text-center font-mono">{d.righe?.length || 0}</td>
                <td className="py-2 px-4 text-right font-mono font-bold">€ {d.imponibile.toFixed(2)}</td>
                <td className="py-2 px-4 text-center">
                  {d.stato_fatturazione === "fatturato" ? (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-emerald-100 text-emerald-700"><CheckCircle size={10} weight="fill" /> {d.fattura_numero || "Fatturato"}</span>
                  ) : (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-amber-100 text-amber-700">Non fatturato</span>
                  )}
                </td>
                <td className="py-2 px-4 text-right">
                  <div className="inline-flex items-center gap-1">
                    <Button variant="ghost" size="icon" onClick={() => openPdf(d)} title="Scarica PDF" data-testid={`pdf-ddt-${d.id}`}><FilePdf size={16} /></Button>
                    {d.stato_fatturazione === "non_fatturato" && (
                      <>
                        <Button variant="ghost" size="icon" onClick={() => openEdit(d)} title="Modifica" data-testid={`edit-ddt-${d.id}`}><PencilSimple size={14} /></Button>
                        <Button variant="ghost" size="icon" onClick={() => delDDT(d)} className="text-red-600" data-testid={`del-ddt-${d.id}`}><Trash size={14} /></Button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {list.length === 0 && <tr><td colSpan="7" className="text-center py-12 text-slate-400">Nessun DDT</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
