import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { ClipboardText, Scan, Camera, CheckCircle, Plus } from "@phosphor-icons/react";
import { toast } from "sonner";
import FileUpload from "../components/FileUpload";
import SignaturePad from "../components/SignaturePad";

export default function Accettazione() {
  const [clienti, setClienti] = useState([]);
  const [articoli, setArticoli] = useState([]);
  const [form, setForm] = useState({
    cliente_id: "",
    data_ritiro: new Date().toISOString().split("T")[0],
    operatore: "",
    peso_totale: 0,
    quantita_totale: 0,
    anomalie: "",
    foto_urls: [],
    note: "",
  });
  const [lotti, setLotti] = useState([{ articolo_id: "", quantita: 10, peso: 5, priorita: "normale" }]);
  const [fotos, setFotos] = useState([]);
  const [firma, setFirma] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      const [c, a] = await Promise.all([api.get("/clienti"), api.get("/articoli")]);
      setClienti(c.data); setArticoli(a.data);
    })();
  }, []);

  const addLotto = () => setLotti([...lotti, { articolo_id: "", quantita: 10, peso: 5, priorita: "normale" }]);
  const updateLotto = (i, patch) => setLotti(lotti.map((l, idx) => idx === i ? { ...l, ...patch } : l));
  const removeLotto = (i) => setLotti(lotti.filter((_, idx) => idx !== i));

  const submit = async (e) => {
    e.preventDefault();
    if (!form.cliente_id) { toast.error("Seleziona cliente"); return; }
    setSaving(true);
    try {
      const quantita_totale = lotti.reduce((s, l) => s + Number(l.quantita || 0), 0);
      const peso_totale = lotti.reduce((s, l) => s + Number(l.peso || 0), 0);
      const ritiro = await api.post("/ritiri", {
        ...form,
        quantita_totale,
        peso_totale,
        foto_urls: fotos.map(f => f.url),
        firma_url: firma?.url || "",
      });
      // Crea lotti
      for (const l of lotti) {
        if (l.articolo_id) {
          await api.post("/lotti", {
            ritiro_id: ritiro.data.id,
            cliente_id: form.cliente_id,
            articolo_id: l.articolo_id,
            quantita: Number(l.quantita),
            peso: Number(l.peso),
            priorita: l.priorita,
          });
        }
      }
      toast.success(`Ritiro ${ritiro.data.numero} registrato con ${lotti.length} lotti`);
      setForm({ ...form, cliente_id: "", operatore: "", anomalie: "", note: "" });
      setLotti([{ articolo_id: "", quantita: 10, peso: 5, priorita: "normale" }]);
      setFotos([]); setFirma(null);
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    setSaving(false);
  };

  return (
    <div>
      <PageHeader
        eyebrow="Workflow"
        title="Accettazione Merce"
        subtitle="Ricezione capi in ingresso. Crea un documento di ritiro con i lotti annessi per avviare la tracciabilità."
      />

      <form onSubmit={submit} className="grid grid-cols-1 lg:grid-cols-3 gap-6" data-testid="accettazione-form">
        <div className="lg:col-span-2 kpi-card">
          <div className="flex items-center gap-3 mb-6 pb-4 border-b border-slate-100">
            <div className="w-10 h-10 rounded-lg bg-indaco/10 flex items-center justify-center">
              <ClipboardText size={20} weight="duotone" className="text-indaco" />
            </div>
            <div>
              <div className="font-display text-xl font-bold">Documento di Ritiro</div>
              <div className="text-xs text-slate-500">Genera un nuovo RIT-*</div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="md:col-span-2">
              <Label>Cliente *</Label>
              <Select value={form.cliente_id} onValueChange={v => setForm({...form, cliente_id: v})}>
                <SelectTrigger data-testid="accettazione-cliente"><SelectValue placeholder="Seleziona cliente" /></SelectTrigger>
                <SelectContent>{clienti.map(c => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div><Label>Data ritiro</Label><Input type="date" value={form.data_ritiro} onChange={e => setForm({...form, data_ritiro: e.target.value})} /></div>
            <div><Label>Operatore</Label><Input value={form.operatore} onChange={e => setForm({...form, operatore: e.target.value})} placeholder="Nome operatore" data-testid="accettazione-operatore" /></div>
            <div className="md:col-span-2"><Label>Anomalie</Label><Textarea rows={2} value={form.anomalie} onChange={e => setForm({...form, anomalie: e.target.value})} placeholder="Capi macchiati, buchi, mancanti..." /></div>
            <div className="md:col-span-2"><Label>Note</Label><Textarea rows={2} value={form.note} onChange={e => setForm({...form, note: e.target.value})} /></div>
          </div>

          <div className="mt-8 pt-6 border-t border-slate-100">
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="font-display text-lg font-bold">Lotti ricevuti</div>
                <div className="text-xs text-slate-500">Ogni riga genera un lotto tracciato</div>
              </div>
              <Button type="button" variant="outline" onClick={addLotto} data-testid="add-lotto-btn"><Plus size={14} className="mr-1" />Aggiungi lotto</Button>
            </div>

            <div className="space-y-3">
              {lotti.map((l, i) => (
                <div key={i} className="grid grid-cols-12 gap-2 items-end p-3 border border-slate-200 rounded-md bg-slate-50/50">
                  <div className="col-span-12 md:col-span-5">
                    <Label className="text-xs">Articolo</Label>
                    <Select value={l.articolo_id} onValueChange={v => updateLotto(i, { articolo_id: v })}>
                      <SelectTrigger data-testid={`lotto-articolo-${i}`}><SelectValue placeholder="Seleziona articolo" /></SelectTrigger>
                      <SelectContent>{articoli.map(a => <SelectItem key={a.id} value={a.id}>{a.codice} - {a.descrizione}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <div className="col-span-4 md:col-span-2"><Label className="text-xs">Quantità</Label><Input type="number" value={l.quantita} onChange={e => updateLotto(i, { quantita: e.target.value })} /></div>
                  <div className="col-span-4 md:col-span-2"><Label className="text-xs">Peso kg</Label><Input type="number" step="0.1" value={l.peso} onChange={e => updateLotto(i, { peso: e.target.value })} /></div>
                  <div className="col-span-4 md:col-span-2">
                    <Label className="text-xs">Priorità</Label>
                    <Select value={l.priorita} onValueChange={v => updateLotto(i, { priorita: v })}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="normale">Normale</SelectItem>
                        <SelectItem value="alta">Alta</SelectItem>
                        <SelectItem value="urgente">Urgente</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="col-span-12 md:col-span-1">
                    <Button type="button" variant="outline" className="w-full text-red-500" onClick={() => removeLotto(i)}>✕</Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Sidebar tools */}
        <div className="space-y-4">
          <div className="kpi-card">
            <div className="overline mb-3">Foto capi</div>
            <FileUpload value={fotos} onChange={setFotos} context="accettazione" label="Scatta/Carica foto" testId="accettazione-foto" />
          </div>

          <div className="kpi-card">
            <div className="overline mb-3">Firma operatore</div>
            <SignaturePad value={firma} onSaved={setFirma} context="accettazione-firma" testId="accettazione-firma" />
          </div>

          <div className="kpi-card">
            <div className="overline mb-3">Integrazioni</div>
            <div className="space-y-2">
              <button type="button" className="w-full flex items-center gap-3 p-3 border border-slate-200 rounded-md hover:bg-slate-50 text-sm" data-testid="barcode-btn">
                <Scan size={20} className="text-indaco" weight="duotone" /><span>Scanner Barcode/RFID</span>
              </button>
            </div>
          </div>

          <div className="kpi-card bg-gradient-to-br from-indaco to-indaco-dark text-white border-0">
            <div className="overline text-white/60 mb-2">Riepilogo</div>
            <div className="font-display text-4xl font-bold mb-1">{lotti.length}</div>
            <div className="text-sm text-white/70 mb-4">lotti in accettazione</div>
            <div className="pt-4 border-t border-white/20 space-y-1 text-sm">
              <div className="flex justify-between"><span className="text-white/70">Capi totali</span><span className="font-mono font-bold">{lotti.reduce((s, l) => s + Number(l.quantita || 0), 0)}</span></div>
              <div className="flex justify-between"><span className="text-white/70">Peso totale</span><span className="font-mono font-bold">{lotti.reduce((s, l) => s + Number(l.peso || 0), 0).toFixed(1)} kg</span></div>
            </div>
            <Button type="submit" disabled={saving} className="w-full mt-6 bg-white text-indaco hover:bg-slate-100" data-testid="save-ritiro-btn">
              <CheckCircle size={18} weight="bold" className="mr-2" />
              {saving ? "Registrazione..." : "Registra Ritiro"}
            </Button>
          </div>
        </div>
      </form>
    </div>
  );
}
