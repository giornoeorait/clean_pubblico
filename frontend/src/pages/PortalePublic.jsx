import React, { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { toast } from "sonner";
import { ShoppingCart, Plus, Minus, CheckCircle, Warning, Package, Buildings, Truck, CurrencyEur } from "@phosphor-icons/react";

const BACKEND = process.env.REACT_APP_BACKEND_URL;

function inDays(n) { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); }

export default function PortalePublic() {
  const { token } = useParams();
  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);
  const [cart, setCart] = useState({}); // articolo_id -> quantita
  const [dataConsegna, setDataConsegna] = useState(inDays(3));
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(null);

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(`${BACKEND}/api/public/portale/${token}`);
      setInfo(data);
    } catch (e) {
      setError(e.response?.status === 404 ? "Link non valido o scaduto" : "Errore caricamento");
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const setQty = (aid, qty) => {
    const q = Math.max(0, parseInt(qty) || 0);
    if (q === 0) { const nc = { ...cart }; delete nc[aid]; setCart(nc); }
    else setCart({ ...cart, [aid]: q });
  };

  const articoliOrdinati = (info?.articoli || []);
  const totale = Object.entries(cart).reduce((acc, [aid, q]) => {
    const a = articoliOrdinati.find(x => x.id === aid);
    return acc + (a?.prezzo || 0) * q;
  }, 0);
  const nRighe = Object.keys(cart).length;

  const submit = async () => {
    if (!nRighe) { toast.error("Aggiungi almeno un articolo"); return; }
    if (!dataConsegna) { toast.error("Seleziona data consegna"); return; }
    setSubmitting(true);
    try {
      const payload = {
        data_consegna_richiesta: dataConsegna,
        righe: Object.entries(cart).map(([articolo_id, quantita]) => ({ articolo_id, quantita: parseInt(quantita) || 0 })),
        note_cliente: note,
      };
      const { data } = await axios.post(`${BACKEND}/api/public/portale/${token}/ordinativo`, payload);
      setSuccess(data);
      setCart({}); setNote("");
    } catch (e) { toast.error(e.response?.data?.detail || "Errore invio"); }
    finally { setSubmitting(false); }
  };

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 p-6">
        <div className="max-w-md w-full bg-white rounded-2xl border border-red-200 p-8 text-center">
          <Warning size={48} weight="fill" className="mx-auto text-red-500 mb-4" />
          <h1 className="font-display font-bold text-xl text-slate-800">{error}</h1>
          <p className="text-sm text-slate-500 mt-2">Contatta il tuo fornitore per ricevere un nuovo link.</p>
        </div>
      </div>
    );
  }
  if (!info) return <div className="min-h-screen flex items-center justify-center text-slate-400 font-mono text-sm">Caricamento portale…</div>;

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-emerald-50 to-indaco/5 p-6">
        <div className="max-w-lg w-full bg-white rounded-2xl border-2 border-emerald-500 p-8 text-center" data-testid="portale-success">
          <CheckCircle size={64} weight="fill" className="mx-auto text-emerald-500 mb-4" />
          <h1 className="font-display font-bold text-2xl text-slate-800">Ordinativo inviato!</h1>
          <p className="font-mono text-indaco text-lg font-bold mt-2">{success.numero}</p>
          <div className="mt-6 p-4 bg-slate-50 rounded-lg text-left">
            <div className="flex justify-between text-sm"><span className="text-slate-500">Righe:</span><span className="font-mono font-bold">{success.righe.length}</span></div>
            <div className="flex justify-between text-sm mt-1"><span className="text-slate-500">Consegna richiesta:</span><span className="font-mono font-bold">{new Date(success.data_consegna_richiesta).toLocaleDateString("it-IT")}</span></div>
            <div className="flex justify-between text-base mt-3 pt-3 border-t border-slate-200"><span className="font-semibold">Totale stimato:</span><span className="font-mono font-bold text-indaco text-xl">€ {success.totale.toFixed(2)}</span></div>
          </div>
          <Button onClick={() => setSuccess(null)} className="mt-6 bg-indaco hover:bg-indaco-dark" data-testid="portale-new-order-btn">Nuovo ordinativo</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-slate-400 text-xs font-mono uppercase tracking-widest">
              <Buildings size={12} /> Fornitore
            </div>
            <div className="font-display font-bold text-slate-900 truncate">{info.fornitore.nome || info.fornitore.ragione_sociale}</div>
          </div>
          <div className="text-right min-w-0">
            <div className="text-xs text-slate-400 font-mono uppercase tracking-widest">Portale ordinativi</div>
            <div className="font-semibold text-indaco truncate">{info.cliente.denominazione_struttura}</div>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8">
        <div className="mb-6">
          <h1 className="font-display text-3xl font-bold text-slate-900">Nuovo ordinativo</h1>
          <p className="text-slate-500 mt-1">
            Seleziona gli articoli che vuoi ricevere.
            {info.listino && <> Prezzi <b>listino {info.listino.nome}</b> ({info.listino.tipo}).</>}
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Catalogo */}
          <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 overflow-hidden" data-testid="portale-catalogo">
            <div className="px-5 py-3 border-b border-slate-200 flex items-center gap-2">
              <Package size={18} className="text-indaco" weight="duotone" />
              <h2 className="font-display font-bold">Catalogo articoli</h2>
            </div>
            {info.articoli.length === 0 ? (
              <div className="py-12 text-center text-slate-400">Nessun articolo disponibile. Contatta il fornitore.</div>
            ) : (
              <div className="divide-y divide-slate-100">
                {info.articoli.map(a => {
                  const q = cart[a.id] || 0;
                  const step = Math.max(1, parseInt(a.multiplo_quantita) || 1);
                  return (
                    <div key={a.id} className="flex items-center gap-4 p-4" data-testid={`portale-art-${a.codice}`}>
                      <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-celeste/20 to-indaco/20 flex items-center justify-center flex-shrink-0">
                        <Package size={18} className="text-indaco" weight="duotone" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-semibold text-slate-900 truncate">{a.descrizione}</div>
                        <div className="text-xs text-slate-500 font-mono">
                          {a.codice} · € {a.prezzo.toFixed(2)}/{a.unita_misura}
                          {step > 1 && <span className="ml-2 text-amber-600">· solo multipli di {step}</span>}
                        </div>
                      </div>
                      <div className="flex items-center gap-1">
                        <button onClick={() => setQty(a.id, Math.max(0, q - step))} className="w-8 h-8 rounded-md border border-slate-200 hover:bg-slate-50 flex items-center justify-center"><Minus size={14} /></button>
                        <Input
                          type="number" min={0} step={step} value={q}
                          onChange={(e) => {
                            const v = parseInt(e.target.value) || 0;
                            // snap to nearest multiple (round down to be safe)
                            const snapped = step > 1 ? Math.floor(v / step) * step : v;
                            setQty(a.id, Math.max(0, snapped));
                          }}
                          className="w-16 h-8 text-center font-mono"
                          data-testid={`portale-qty-${a.codice}`}
                        />
                        <button onClick={() => setQty(a.id, q + step)} className="w-8 h-8 rounded-md border border-slate-200 hover:bg-slate-50 flex items-center justify-center"><Plus size={14} /></button>
                      </div>
                      <div className="text-right w-24 font-mono text-sm">
                        {q > 0 ? <span className="font-bold text-indaco">€ {(q * a.prezzo).toFixed(2)}</span> : <span className="text-slate-300">—</span>}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Carrello */}
          <aside className="bg-white rounded-2xl border border-slate-200 p-5 self-start sticky top-6" data-testid="portale-carrello">
            <div className="flex items-center gap-2 mb-4">
              <ShoppingCart size={18} className="text-indaco" weight="duotone" />
              <h2 className="font-display font-bold">Riepilogo</h2>
            </div>
            <div>
              <Label>Data consegna richiesta *</Label>
              <Input type="date" value={dataConsegna} onChange={e => setDataConsegna(e.target.value)} className="mt-1" data-testid="portale-data" />
            </div>
            <div className="mt-3">
              <Label>Note</Label>
              <Textarea rows={3} value={note} onChange={e => setNote(e.target.value)} placeholder="Orario preferito, istruzioni speciali…" data-testid="portale-note" />
            </div>
            <div className="mt-4 p-3 bg-slate-50 rounded-lg space-y-1 text-sm">
              <div className="flex justify-between"><span className="text-slate-500">Righe</span><span className="font-mono font-bold">{nRighe}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Pezzi totali</span><span className="font-mono font-bold">{Object.values(cart).reduce((a, b) => a + b, 0)}</span></div>
              <div className="flex justify-between pt-2 mt-2 border-t border-slate-200">
                <span className="font-semibold flex items-center gap-1"><CurrencyEur size={14} />Totale stimato</span>
                <span className="font-mono font-bold text-indaco text-lg">€ {totale.toFixed(2)}</span>
              </div>
            </div>
            <Button onClick={submit} disabled={submitting || nRighe === 0} className="w-full mt-4 bg-indaco hover:bg-indaco-dark" data-testid="portale-submit-btn">
              <Truck size={16} className="mr-2" />
              {submitting ? "Invio…" : `Invia ordinativo`}
            </Button>
            <p className="text-[11px] text-slate-400 mt-3 text-center">
              I prezzi sono indicativi. L'importo finale verrà confermato sulla fattura.
            </p>
          </aside>
        </div>
      </main>
    </div>
  );
}
