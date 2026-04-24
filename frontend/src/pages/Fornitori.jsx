import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Plus, MagnifyingGlass, Factory, PencilSimple, Trash, Eye, Warning, Receipt, Truck } from "@phosphor-icons/react";
import { toast } from "sonner";

const EMPTY = {
  ragione_sociale: "", partita_iva: "", codice_fiscale: "", indirizzo: "",
  email: "", telefono: "", pec: "", codice_sdi: "",
  iban: "", sito: "", categoria: "prodotti", referente: "",
  condizioni_pagamento: "30gg", note: "", attivo: true,
};

const REQUIRED = ["ragione_sociale", "partita_iva", "indirizzo", "email", "telefono"];

const CATEGORIE = [
  { v: "prodotti", l: "Prodotti (detergenti, chimici, consumabili)" },
  { v: "utenze", l: "Utenze (gas, luce, acqua)" },
  { v: "servizi", l: "Servizi (consulenze, software)" },
  { v: "manutenzioni", l: "Manutenzioni (macchinari, officine)" },
  { v: "trasporti", l: "Trasporti / logistica" },
  { v: "altro", l: "Altro" },
];

export default function Fornitori() {
  const [list, setList] = useState([]);
  const [q, setQ] = useState("");
  const [catFilter, setCatFilter] = useState("all");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [editing, setEditing] = useState(null);
  const [profile, setProfile] = useState(null);

  const fetchList = async () => {
    const params = [];
    if (q) params.push(`q=${encodeURIComponent(q)}`);
    if (catFilter !== "all") params.push(`categoria=${catFilter}`);
    const { data } = await api.get("/fornitori" + (params.length ? `?${params.join("&")}` : ""));
    setList(data);
  };
  useEffect(() => { fetchList(); }, [q, catFilter]);

  const missingReq = REQUIRED.filter(k => !(form[k] || "").trim());
  const canSave = missingReq.length === 0;

  const save = async (e) => {
    e.preventDefault();
    if (!canSave) { toast.error(`Campi obbligatori: ${missingReq.join(", ")}`); return; }
    try {
      if (editing) { await api.patch(`/fornitori/${editing}`, form); toast.success("Fornitore aggiornato"); }
      else { await api.post("/fornitori", form); toast.success("Fornitore creato"); }
      setOpen(false); setEditing(null); setForm(EMPTY);
      fetchList();
    } catch (e2) { toast.error(e2.response?.data?.detail || "Errore"); }
  };

  const edit = (f) => { setForm({ ...EMPTY, ...f }); setEditing(f.id); setOpen(true); };
  const del = async (id) => {
    if (!window.confirm("Eliminare fornitore? Non possibile se ha documenti collegati.")) return;
    try { await api.delete(`/fornitori/${id}`); toast.success("Eliminato"); fetchList(); }
    catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const openProfile = async (f) => {
    try {
      const { data } = await api.get(`/fornitori/${f.id}/profilo`);
      setProfile(data);
    } catch { toast.error("Errore profilo"); }
  };

  const req = (key) => (
    <span className={`text-red-500 ml-0.5 ${(form[key] || "").trim() ? "text-emerald-500" : ""}`}>*</span>
  );

  return (
    <div>
      <PageHeader
        eyebrow="Anagrafica"
        title="Fornitori"
        subtitle="Chimici, utenze, servizi, manutenzioni. Ogni fornitore collega i propri DDT ricevuti e fatture passive."
        actions={
          <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setEditing(null); setForm(EMPTY); } }}>
            <DialogTrigger asChild>
              <Button className="bg-indaco hover:bg-indaco-dark" data-testid="new-fornitore-btn"><Plus size={16} weight="bold" className="mr-1" /> Nuovo Fornitore</Button>
            </DialogTrigger>
            <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
              <DialogHeader><DialogTitle>{editing ? "Modifica fornitore" : "Nuovo fornitore"}</DialogTitle></DialogHeader>
              <form onSubmit={save} className="space-y-5" data-testid="fornitore-form">
                <section className="border border-slate-200 rounded-lg p-4 bg-slate-50/40">
                  <div className="flex items-center gap-2 mb-3">
                    <Factory size={18} className="text-indaco" weight="duotone" />
                    <h4 className="font-display font-bold text-sm">Identificazione fiscale</h4>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="col-span-2"><Label>Ragione sociale{req("ragione_sociale")}</Label><Input value={form.ragione_sociale} onChange={e => setForm({...form, ragione_sociale: e.target.value})} data-testid="forn-rs" /></div>
                    <div><Label>Partita IVA{req("partita_iva")}</Label><Input value={form.partita_iva} onChange={e => setForm({...form, partita_iva: e.target.value})} placeholder="IT01234567890" data-testid="forn-piva" /></div>
                    <div><Label>Codice fiscale</Label><Input value={form.codice_fiscale} onChange={e => setForm({...form, codice_fiscale: e.target.value})} /></div>
                    <div className="col-span-2"><Label>Indirizzo sede{req("indirizzo")}</Label><Input value={form.indirizzo} onChange={e => setForm({...form, indirizzo: e.target.value})} /></div>
                    <div><Label>Email{req("email")}</Label><Input type="email" value={form.email} onChange={e => setForm({...form, email: e.target.value})} /></div>
                    <div><Label>Telefono{req("telefono")}</Label><Input value={form.telefono} onChange={e => setForm({...form, telefono: e.target.value})} /></div>
                    <div><Label>PEC</Label><Input value={form.pec} onChange={e => setForm({...form, pec: e.target.value})} /></div>
                    <div><Label>Codice SDI</Label><Input value={form.codice_sdi} onChange={e => setForm({...form, codice_sdi: e.target.value})} placeholder="ABCDE12" /></div>
                    <div className="col-span-2"><Label>IBAN</Label><Input value={form.iban} onChange={e => setForm({...form, iban: e.target.value})} placeholder="IT..." /></div>
                    <div><Label>Sito web</Label><Input value={form.sito} onChange={e => setForm({...form, sito: e.target.value})} placeholder="https://..." /></div>
                    <div><Label>Referente</Label><Input value={form.referente} onChange={e => setForm({...form, referente: e.target.value})} /></div>
                  </div>
                </section>

                <section className="border border-slate-200 rounded-lg p-4 bg-celeste/5">
                  <div className="flex items-center gap-2 mb-3">
                    <h4 className="font-display font-bold text-sm">Categoria & condizioni</h4>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label>Categoria</Label>
                      <Select value={form.categoria} onValueChange={v => setForm({...form, categoria: v})}>
                        <SelectTrigger data-testid="forn-categoria"><SelectValue /></SelectTrigger>
                        <SelectContent>{CATEGORIE.map(c => <SelectItem key={c.v} value={c.v}>{c.l}</SelectItem>)}</SelectContent>
                      </Select>
                    </div>
                    <div><Label>Condizioni pagamento</Label><Input value={form.condizioni_pagamento} onChange={e => setForm({...form, condizioni_pagamento: e.target.value})} placeholder="30gg DF" /></div>
                    <div className="col-span-2"><Label>Note</Label><Input value={form.note} onChange={e => setForm({...form, note: e.target.value})} /></div>
                  </div>
                </section>

                {!canSave && (
                  <div className="flex items-center gap-2 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
                    <Warning size={16} weight="fill" />
                    <span>Campi mancanti: <b>{missingReq.join(", ")}</b></span>
                  </div>
                )}

                <div className="flex justify-end gap-2">
                  <Button type="button" variant="outline" onClick={() => setOpen(false)}>Annulla</Button>
                  <Button type="submit" disabled={!canSave} className="bg-indaco hover:bg-indaco-dark" data-testid="save-fornitore-btn">Salva fornitore</Button>
                </div>
              </form>
            </DialogContent>
          </Dialog>
        }
      />

      <div className="kpi-card mb-6 flex gap-3 flex-wrap items-center">
        <div className="relative flex-1 min-w-[260px]">
          <MagnifyingGlass size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Cerca per ragione sociale, P.IVA…"
            className="w-full pl-10 pr-4 py-2 border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indaco"
            data-testid="fornitori-search" />
        </div>
        <Select value={catFilter} onValueChange={setCatFilter}>
          <SelectTrigger className="w-64" data-testid="fornitori-cat-filter"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tutte le categorie</SelectItem>
            {CATEGORIE.map(c => <SelectItem key={c.v} value={c.v}>{c.l}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      <div className="kpi-card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr><th>Ragione sociale</th><th>Categoria</th><th>P.IVA</th><th>Contatti</th><th>Azioni</th></tr>
            </thead>
            <tbody>
              {list.map(f => {
                const cat = CATEGORIE.find(c => c.v === f.categoria);
                return (
                  <tr key={f.id} data-testid={`fornitore-row-${f.id}`}>
                    <td>
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-amber-100 to-orange-200 flex items-center justify-center flex-shrink-0">
                          <Factory size={16} className="text-amber-700" weight="duotone" />
                        </div>
                        <div>
                          <div className="font-medium text-slate-900">{f.ragione_sociale}</div>
                          <div className="text-xs text-slate-500 truncate max-w-xs">{f.indirizzo}</div>
                        </div>
                      </div>
                    </td>
                    <td><span className="px-2 py-0.5 text-xs rounded-full bg-amber-50 text-amber-700 border border-amber-200">{cat?.l.split(" (")[0] || f.categoria}</span></td>
                    <td className="font-mono text-xs">{f.partita_iva}</td>
                    <td>
                      <div className="text-xs">{f.email}</div>
                      <div className="text-[11px] text-slate-500 font-mono">{f.telefono}</div>
                    </td>
                    <td>
                      <div className="flex gap-1">
                        <button onClick={() => openProfile(f)} className="p-1.5 hover:bg-indaco/10 rounded" title="Profilo" data-testid={`forn-profile-${f.id}`}><Eye size={16} className="text-indaco" /></button>
                        <button onClick={() => edit(f)} className="p-1.5 hover:bg-slate-100 rounded" data-testid={`forn-edit-${f.id}`}><PencilSimple size={16} className="text-slate-500" /></button>
                        <button onClick={() => del(f.id)} className="p-1.5 hover:bg-red-50 rounded" data-testid={`forn-del-${f.id}`}><Trash size={16} className="text-red-500" /></button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {list.length === 0 && <tr><td colSpan={5} className="text-center py-8 text-slate-400">Nessun fornitore. Crea il primo!</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      <Dialog open={!!profile} onOpenChange={(o) => { if (!o) setProfile(null); }}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          {profile && (
            <>
              <DialogHeader><DialogTitle className="flex items-center gap-2"><Factory size={20} className="text-amber-700" />{profile.fornitore.ragione_sociale}</DialogTitle></DialogHeader>
              <div className="grid grid-cols-4 gap-3 mb-4">
                <div className="kpi-card p-3"><div className="text-[11px] uppercase text-slate-500">DDT ricevuti</div><div className="text-2xl font-display font-bold">{profile.stats.ddt_totali}</div></div>
                <div className="kpi-card p-3"><div className="text-[11px] uppercase text-slate-500">Fatture</div><div className="text-2xl font-display font-bold">{profile.stats.fatture_totali}</div></div>
                <div className="kpi-card p-3"><div className="text-[11px] uppercase text-slate-500">Spesa totale</div><div className="text-2xl font-display font-bold text-indaco">€ {profile.stats.spesa_totale.toFixed(2)}</div></div>
                <div className="kpi-card p-3"><div className="text-[11px] uppercase text-slate-500">Da pagare</div><div className="text-2xl font-display font-bold text-red-600">€ {profile.stats.da_pagare_totale.toFixed(2)}</div></div>
              </div>
              <div className="space-y-4">
                <section>
                  <h4 className="font-display font-bold mb-2 flex items-center gap-2"><Truck size={16} /> DDT ricevuti</h4>
                  <div className="border rounded overflow-hidden">
                    <table className="data-table"><thead><tr><th>Numero int.</th><th>Rif. fornitore</th><th>Data</th><th>Totale</th><th>Stato</th></tr></thead><tbody>
                      {profile.ddts.map(d => (
                        <tr key={d.id}><td className="font-mono text-xs">{d.numero}</td><td className="text-xs">{d.numero_fornitore}</td><td className="text-xs">{d.data}</td><td className="text-right font-mono">€ {d.totale.toFixed(2)}</td><td><span className={`px-2 py-0.5 text-xs rounded-full ${d.stato_fatturazione === "fatturato" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>{d.stato_fatturazione}</span></td></tr>
                      ))}
                      {profile.ddts.length === 0 && <tr><td colSpan={5} className="text-center text-slate-400 py-4">Nessun DDT</td></tr>}
                    </tbody></table>
                  </div>
                </section>
                <section>
                  <h4 className="font-display font-bold mb-2 flex items-center gap-2"><Receipt size={16} /> Fatture ricevute</h4>
                  <div className="border rounded overflow-hidden">
                    <table className="data-table"><thead><tr><th>Numero int.</th><th>Rif. fornitore</th><th>Data</th><th>Scadenza</th><th>Totale</th><th>Stato</th></tr></thead><tbody>
                      {profile.fatture.map(f => (
                        <tr key={f.id}><td className="font-mono text-xs">{f.numero}</td><td className="text-xs">{f.numero_fornitore}</td><td className="text-xs">{f.data}</td><td className="text-xs">{f.data_scadenza || "—"}</td><td className="text-right font-mono">€ {f.totale.toFixed(2)}</td><td><span className={`px-2 py-0.5 text-xs rounded-full ${f.stato_pagamento === "pagata" ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}>{f.stato_pagamento}</span></td></tr>
                      ))}
                      {profile.fatture.length === 0 && <tr><td colSpan={6} className="text-center text-slate-400 py-4">Nessuna fattura</td></tr>}
                    </tbody></table>
                  </div>
                </section>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
