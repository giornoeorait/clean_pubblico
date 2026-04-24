import React, { useCallback, useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { CurrencyEur, CheckCircle, Eye, MagnifyingGlass, Warning } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function Sospesi() {
  const [fatture, setFatture] = useState([]);
  const [totale, setTotale] = useState(0);
  const [clienti, setClienti] = useState([]);
  const [fCli, setFCli] = useState("all");
  const [fDal, setFDal] = useState("");
  const [fAl, setFAl] = useState("");
  const [fNum, setFNum] = useState("");
  const [detail, setDetail] = useState(null);
  const [incassoOpen, setIncassoOpen] = useState(null);
  const [metodo, setMetodo] = useState("bonifico");
  const [dataIncasso, setDataIncasso] = useState("");

  const fetchData = useCallback(async () => {
    const p = [];
    if (fCli !== "all") p.push(`cliente_id=${fCli}`);
    if (fDal) p.push(`dal=${fDal}`);
    if (fAl) p.push(`al=${fAl}`);
    if (fNum) p.push(`numero=${fNum}`);
    const q = p.length ? `?${p.join("&")}` : "";
    const [s, c] = await Promise.all([
      api.get(`/sospesi${q}`),
      api.get("/clienti"),
    ]);
    setFatture(s.data.fatture); setTotale(s.data.totale_sospesi); setClienti(c.data);
  }, [fCli, fDal, fAl, fNum]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const openDetail = async (f) => {
    try { const { data } = await api.get(`/fatture/${f.id}`); setDetail(data); }
    catch { toast.error("Errore caricamento"); }
  };

  const incassa = async () => {
    try {
      await api.post(`/fatture/${incassoOpen.id}/incassa`, {
        metodo,
        data_incasso: dataIncasso || undefined,
      });
      toast.success(`Fattura ${incassoOpen.numero} incassata`);
      setIncassoOpen(null); setDataIncasso(""); fetchData();
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const resetFilters = () => { setFCli("all"); setFDal(""); setFAl(""); setFNum(""); };

  return (
    <div>
      <PageHeader
        eyebrow="Contabilità"
        title="Sospesi — Fatture da incassare"
        subtitle="Elenco fatture aperte. Filtra per cliente, data e numero. Clicca 'Incassa' per chiudere la partita."
      />

      {/* Totale KPI */}
      <div className="kpi-card mb-4 bg-gradient-to-r from-amber-500 to-orange-500 text-white border-0" data-testid="sospesi-kpi">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-white/20 flex items-center justify-center"><CurrencyEur size={28} weight="duotone" /></div>
            <div>
              <div className="overline text-white/80">Totale sospesi</div>
              <div className="font-display text-3xl font-bold">€ {totale.toLocaleString("it-IT", {minimumFractionDigits: 2})}</div>
            </div>
          </div>
          <div className="text-right">
            <div className="font-display text-4xl font-bold">{fatture.length}</div>
            <div className="text-xs uppercase tracking-widest text-white/80">fatture aperte</div>
          </div>
        </div>
      </div>

      {/* Filtri */}
      <div className="kpi-card mb-4">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3 items-end">
          <div>
            <Label className="text-xs">Cliente</Label>
            <Select value={fCli} onValueChange={setFCli}>
              <SelectTrigger data-testid="sosp-f-cliente"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Tutti</SelectItem>
                {clienti.map(c => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div><Label className="text-xs">Dal</Label><Input type="date" value={fDal} onChange={e => setFDal(e.target.value)} data-testid="sosp-f-dal" /></div>
          <div><Label className="text-xs">Al</Label><Input type="date" value={fAl} onChange={e => setFAl(e.target.value)} data-testid="sosp-f-al" /></div>
          <div><Label className="text-xs">N° fattura</Label><Input placeholder="FT-2026-..." value={fNum} onChange={e => setFNum(e.target.value)} data-testid="sosp-f-numero" /></div>
          <Button variant="outline" onClick={resetFilters}>Reset</Button>
        </div>
      </div>

      {/* Lista */}
      <div className="kpi-card p-0 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs uppercase tracking-widest text-slate-500 border-b border-slate-200">
            <tr>
              <th className="text-left py-3 px-4">N°</th>
              <th className="text-left py-3 px-4">Data</th>
              <th className="text-left py-3 px-4">Scadenza</th>
              <th className="text-left py-3 px-4">Cliente</th>
              <th className="text-center py-3 px-4">DDT</th>
              <th className="text-right py-3 px-4">Totale</th>
              <th className="text-right py-3 px-4">Azioni</th>
            </tr>
          </thead>
          <tbody>
            {fatture.map(f => {
              const scad = f.scadenza ? new Date(f.scadenza) : null;
              const overdue = scad && scad < new Date();
              return (
                <tr key={f.id} className="border-b border-slate-100" data-testid={`sosp-${f.id}`}>
                  <td className="py-2 px-4 font-mono font-bold">{f.numero}</td>
                  <td className="py-2 px-4">{new Date(f.data).toLocaleDateString("it-IT")}</td>
                  <td className="py-2 px-4">
                    {scad ? (
                      <span className={overdue ? "text-red-600 font-bold flex items-center gap-1" : ""}>
                        {overdue && <Warning size={12} weight="fill" />}
                        {scad.toLocaleDateString("it-IT")}
                      </span>
                    ) : "—"}
                  </td>
                  <td className="py-2 px-4">{f.cliente_nome}</td>
                  <td className="py-2 px-4 text-center text-xs text-slate-500">{f.ddt_numeri?.length || 0}</td>
                  <td className="py-2 px-4 text-right font-mono font-bold">€ {f.totale.toFixed(2)}</td>
                  <td className="py-2 px-4 text-right space-x-1">
                    <Button variant="ghost" size="icon" onClick={() => openDetail(f)}><Eye size={14} /></Button>
                    <Button size="sm" onClick={() => setIncassoOpen(f)} className="bg-emerald-600 hover:bg-emerald-700" data-testid={`incassa-${f.id}`}>
                      <CheckCircle size={12} className="mr-1" />Incassa
                    </Button>
                  </td>
                </tr>
              );
            })}
            {fatture.length === 0 && <tr><td colSpan="7" className="text-center py-12 text-slate-400">Nessuna fattura sospesa 🎉</td></tr>}
          </tbody>
        </table>
      </div>

      {/* Dettaglio fattura */}
      <Dialog open={!!detail} onOpenChange={(o) => { if (!o) setDetail(null); }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>Fattura {detail?.numero}</DialogTitle></DialogHeader>
          {detail && (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-2">
                <div><div className="overline">Cliente</div><div className="font-semibold">{detail.cliente_nome}</div></div>
                <div><div className="overline">Data</div><div>{new Date(detail.data).toLocaleDateString("it-IT")}</div></div>
              </div>
              <div>
                <div className="overline mb-1">DDT inclusi ({detail.ddts?.length || 0})</div>
                <div className="space-y-1">
                  {(detail.ddts || []).map(d => (
                    <div key={d.id} className="flex justify-between text-xs font-mono py-1 border-b border-slate-100">
                      <span>{d.numero} — {new Date(d.data).toLocaleDateString("it-IT")}</span>
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

      {/* Incasso dialog */}
      <Dialog open={!!incassoOpen} onOpenChange={(o) => { if (!o) setIncassoOpen(null); }}>
        <DialogContent>
          <DialogHeader><DialogTitle>Incassa fattura {incassoOpen?.numero}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="text-sm">Totale da incassare: <span className="font-bold text-indaco">€ {incassoOpen?.totale.toFixed(2)}</span></div>
            <div>
              <Label>Metodo</Label>
              <Select value={metodo} onValueChange={setMetodo}>
                <SelectTrigger data-testid="incasso-metodo"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="bonifico">Bonifico</SelectItem>
                  <SelectItem value="contanti">Contanti</SelectItem>
                  <SelectItem value="carta">Carta</SelectItem>
                  <SelectItem value="altro">Altro</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Data incasso (vuoto = oggi)</Label>
              <Input type="date" value={dataIncasso} onChange={e => setDataIncasso(e.target.value)} />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setIncassoOpen(null)}>Annulla</Button>
              <Button onClick={incassa} className="bg-emerald-600 hover:bg-emerald-700" data-testid="confirm-incasso-btn"><CheckCircle size={14} className="mr-1" />Conferma incasso</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
