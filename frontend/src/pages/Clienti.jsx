import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import ImportClientiDialog from "../components/ImportClientiDialog";
import { clientePrimary, clienteSecondary } from "../lib/clienteLabel";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Plus, MagnifyingGlass, Buildings, PencilSimple, Trash, Eye, CheckCircle, Warning, Receipt, Truck, CurrencyEur, Link as LinkIcon, Copy, Prohibit, EnvelopeSimple } from "@phosphor-icons/react";
import { toast } from "sonner";

const EMPTY = {
  ragione_sociale: "", partita_iva: "", codice_fiscale: "", indirizzo: "",
  email: "", telefono: "", pec: "", codice_sdi: "",
  denominazione_struttura: "", indirizzo_scarico: "",
  tipologia: "hotel", listino_id: "",
  condizioni_pagamento: "30gg", giorni_ritiro: [], note: "", attivo: true,
};

const REQUIRED_RS = ["ragione_sociale", "partita_iva", "indirizzo", "email", "telefono"];

export default function Clienti() {
  const [list, setList] = useState([]);
  const [listini, setListini] = useState([]);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [editing, setEditing] = useState(null);
  const [profile, setProfile] = useState(null);

  const fetchList = async () => {
    const { data } = await api.get("/clienti" + (q ? `?q=${encodeURIComponent(q)}` : ""));
    setList(data);
  };
  const fetchListini = async () => {
    try { const { data } = await api.get("/listini?solo_attivi=true"); setListini(data); } catch { /* ignore */ }
  };
  useEffect(() => { fetchList(); }, [q]);
  useEffect(() => { fetchListini(); }, []);

  const missingReq = REQUIRED_RS.filter(k => !(form[k] || "").trim());
  const canSave = missingReq.length === 0;

  const save = async (e) => {
    e.preventDefault();
    if (!canSave) { toast.error(`Compila i campi obbligatori: ${missingReq.join(", ")}`); return; }
    try {
      const payload = { ...form };
      if (!payload.listino_id) delete payload.listino_id;
      if (editing) { await api.patch(`/clienti/${editing}`, payload); toast.success("Cliente aggiornato"); }
      else { await api.post("/clienti", payload); toast.success("Cliente creato"); }
      setOpen(false); setEditing(null); setForm(EMPTY);
      fetchList();
    } catch (e2) { toast.error(e2.response?.data?.detail || "Errore"); }
  };

  const edit = (c) => { setForm({ ...EMPTY, ...c, listino_id: c.listino_id || "" }); setEditing(c.id); setOpen(true); };
  const del = async (id) => {
    if (!window.confirm("Eliminare cliente?")) return;
    await api.delete(`/clienti/${id}`); toast.success("Eliminato"); fetchList();
  };

  const openProfile = async (c) => {
    try {
      const { data } = await api.get(`/clienti/${c.id}/profilo`);
      setProfile({ ...data, _cid: c.id });
    } catch (e) {
      toast.error("Errore caricamento profilo");
    }
  };

  const generaPortale = async () => {
    try {
      const { data } = await api.post(`/clienti/${profile._cid}/portale-token`);
      const fullUrl = `${window.location.origin}${data.url_path}`;
      await openProfile({ id: profile._cid });
      navigator.clipboard?.writeText(fullUrl).catch(() => {});
      toast.success("Link portale creato e copiato negli appunti");
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };
  const revocaPortale = async () => {
    if (!window.confirm("Revocare il link portale del cliente?")) return;
    try {
      await api.delete(`/clienti/${profile._cid}/portale-token`);
      await openProfile({ id: profile._cid });
      toast.success("Link revocato");
    } catch (e) { toast.error("Errore"); }
  };
  const copiaLink = () => {
    if (!profile?.cliente?.portale_token) return;
    const fullUrl = `${window.location.origin}/ordina/${profile.cliente.portale_token}`;
    navigator.clipboard?.writeText(fullUrl).catch(() => {});
    toast.success("Link copiato");
  };

  const inviaLinkEmail = async (tipo) => {
    if (!profile?._cid) return;
    const cliEmail = profile.cliente?.email;
    if (!cliEmail) { toast.error("Email cliente mancante — aggiorna l'anagrafica"); return; }
    if (!window.confirm(`Inviare il link ${tipo === "diretto" ? "diretto" : "self-service"} a ${cliEmail}?`)) return;
    try {
      const { data } = await api.post(`/clienti/${profile._cid}/invia-link-portale`, {
        tipo, base_url: window.location.origin,
      });
      if (data.status === "sent") {
        toast.success(`Email inviata a ${data.to}`);
      } else if (data.status === "logged") {
        toast.warning("SMTP non configurato — link registrato nei log. Configura SMTP da Impostazioni.");
      } else {
        toast.error(data.message || "Invio fallito");
      }
      if (tipo === "diretto") await openProfile({ id: profile._cid }); // refresh per il token appena creato
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const openPdf = async (entity, id) => {
    try {
      const res = await api.get(`/${entity}/${id}/pdf`, { responseType: "blob" });
      window.open(URL.createObjectURL(res.data), "_blank");
    } catch (e) { toast.error("Errore PDF"); }
  };

  const req = (key) => (
    <span className={`text-red-500 ml-0.5 ${(form[key] || "").trim() ? "text-emerald-500" : ""}`}>*</span>
  );

  return (
    <div>
      <PageHeader
        eyebrow="Anagrafica"
        title="Clienti"
        subtitle="Hotel, ospedali, ristoranti, industrie. Identificazione fiscale e denominazione struttura operativa."
        actions={
          <div className="flex gap-2">
          <ImportClientiDialog onImported={fetchList} />
          <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setEditing(null); setForm(EMPTY); } }}>
            <DialogTrigger asChild>
              <Button className="bg-indaco hover:bg-indaco-dark" data-testid="new-cliente-btn"><Plus size={16} weight="bold" className="mr-1" /> Nuovo Cliente</Button>
            </DialogTrigger>
            <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
              <DialogHeader><DialogTitle>{editing ? "Modifica cliente" : "Nuovo cliente"}</DialogTitle></DialogHeader>
              <form onSubmit={save} className="space-y-5" data-testid="cliente-form">

                {/* Sezione 1: Ragione Sociale (identificazione giuridica) */}
                <section className="border border-slate-200 rounded-lg p-4 bg-slate-50/40">
                  <div className="flex items-center gap-2 mb-3">
                    <Buildings size={18} className="text-indaco" weight="duotone" />
                    <h4 className="font-display font-bold text-sm">Ragione sociale <span className="text-[11px] font-mono uppercase text-slate-400">(fatturazione)</span></h4>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="col-span-2"><Label>Ragione sociale{req("ragione_sociale")}</Label><Input value={form.ragione_sociale} onChange={e => setForm({...form, ragione_sociale: e.target.value})} data-testid="cliente-ragione-sociale" /></div>
                    <div><Label>Partita IVA{req("partita_iva")}</Label><Input value={form.partita_iva} onChange={e => setForm({...form, partita_iva: e.target.value})} placeholder="IT01234567890" data-testid="cliente-partita-iva" /></div>
                    <div><Label>Codice fiscale</Label><Input value={form.codice_fiscale} onChange={e => setForm({...form, codice_fiscale: e.target.value})} /></div>
                    <div className="col-span-2"><Label>Indirizzo sede legale{req("indirizzo")}</Label><Input value={form.indirizzo} onChange={e => setForm({...form, indirizzo: e.target.value})} /></div>
                    <div><Label>Email{req("email")}</Label><Input type="email" value={form.email} onChange={e => setForm({...form, email: e.target.value})} /></div>
                    <div><Label>Telefono{req("telefono")}</Label><Input value={form.telefono} onChange={e => setForm({...form, telefono: e.target.value})} /></div>
                    <div><Label>PEC</Label><Input value={form.pec} onChange={e => setForm({...form, pec: e.target.value})} placeholder="cliente@pec.it" data-testid="cliente-pec" /></div>
                    <div><Label>Codice SDI</Label><Input value={form.codice_sdi} onChange={e => setForm({...form, codice_sdi: e.target.value})} placeholder="ABCDE12" data-testid="cliente-sdi" /></div>
                  </div>
                </section>

                {/* Sezione 2: Denominazione struttura (operativa) */}
                <section className="border border-slate-200 rounded-lg p-4 bg-celeste/5">
                  <div className="flex items-center gap-2 mb-3">
                    <Truck size={18} className="text-azzurro" weight="duotone" />
                    <h4 className="font-display font-bold text-sm">Denominazione struttura <span className="text-[11px] font-mono uppercase text-slate-400">(operativa — consegne/ritiri)</span></h4>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="col-span-2"><Label>Denominazione struttura</Label><Input value={form.denominazione_struttura} onChange={e => setForm({...form, denominazione_struttura: e.target.value})} placeholder="es. Hotel Excelsior - reparto biancheria" data-testid="cliente-denominazione" /></div>
                    <div className="col-span-2"><Label>Indirizzo di scarico</Label><Input value={form.indirizzo_scarico} onChange={e => setForm({...form, indirizzo_scarico: e.target.value})} placeholder="Lascia vuoto se coincide con sede legale" data-testid="cliente-indirizzo-scarico" /></div>
                    <div>
                      <Label>Tipologia</Label>
                      <Select value={form.tipologia} onValueChange={v => setForm({...form, tipologia: v})}>
                        <SelectTrigger data-testid="cliente-tipologia"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="hotel">Hotel</SelectItem>
                          <SelectItem value="ristorante">Ristorante</SelectItem>
                          <SelectItem value="ospedale">Ospedale</SelectItem>
                          <SelectItem value="industria">Industria</SelectItem>
                          <SelectItem value="altro">Altro</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div><Label>Condizioni pagamento</Label><Input value={form.condizioni_pagamento} onChange={e => setForm({...form, condizioni_pagamento: e.target.value})} placeholder="30gg DF" /></div>
                    <div className="col-span-2">
                      <Label>Listino associato</Label>
                      <Select value={form.listino_id || "none"} onValueChange={v => setForm({...form, listino_id: v === "none" ? "" : v})}>
                        <SelectTrigger data-testid="cliente-listino"><SelectValue placeholder="Nessuno (usa prezzi default)" /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">— Nessun listino —</SelectItem>
                          {listini.map(l => <SelectItem key={l.id} value={l.id}>{l.nome} · {l.tipo}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </section>

                <div><Label>Note</Label><Input value={form.note} onChange={e => setForm({...form, note: e.target.value})} placeholder="Note libere (non obbligatorio)" /></div>

                {!canSave && (
                  <div className="flex items-center gap-2 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
                    <Warning size={16} weight="fill" />
                    <span>Campi obbligatori mancanti: <b>{missingReq.join(", ")}</b></span>
                  </div>
                )}

                <div className="flex justify-end gap-2">
                  <Button type="button" variant="outline" onClick={() => setOpen(false)}>Annulla</Button>
                  <Button type="submit" disabled={!canSave} className="bg-indaco hover:bg-indaco-dark" data-testid="save-cliente-btn">Salva cliente</Button>
                </div>
              </form>
            </DialogContent>
          </Dialog>
          </div>
        }
      />

      <div className="kpi-card mb-6">
        <div className="relative">
          <MagnifyingGlass size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={q} onChange={e => setQ(e.target.value)}
            placeholder="Cerca per ragione sociale, denominazione, P.IVA…"
            className="w-full pl-10 pr-4 py-2 border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indaco"
            data-testid="clienti-search"
          />
        </div>
      </div>

      <div className="kpi-card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Struttura · Ragione sociale</th>
                <th>Indirizzo scarico</th>
                <th>P.IVA / SDI</th>
                <th>Listino</th>
                <th>Azioni</th>
              </tr>
            </thead>
            <tbody>
              {list.map(c => (
                <tr key={c.id} data-testid={`cliente-row-${c.id}`}>
                  <td>
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-celeste/20 to-indaco/20 flex items-center justify-center flex-shrink-0">
                        <Buildings size={16} className="text-indaco" weight="duotone" />
                      </div>
                      <div className="min-w-0">
                        <div className="font-medium text-slate-900 truncate">{clientePrimary(c)}</div>
                        {clienteSecondary(c) && (
                          <div className="text-[11px] text-slate-400 truncate">{clienteSecondary(c)}</div>
                        )}
                        <div className="text-xs text-slate-500 font-mono truncate">{c.indirizzo}</div>
                      </div>
                    </div>
                  </td>
                  <td>
                    {c.indirizzo_scarico ? (
                      <div className="text-xs text-slate-500 truncate max-w-xs">{c.indirizzo_scarico}</div>
                    ) : (
                      <span className="text-xs text-slate-400 italic">= sede legale</span>
                    )}
                  </td>
                  <td>
                    <div className="font-mono text-xs">{c.partita_iva || "—"}</div>
                    {c.codice_sdi && <div className="text-[11px] text-slate-500 font-mono">SDI: {c.codice_sdi}</div>}
                  </td>
                  <td>
                    {c.listino_id ? (
                      <span className="px-2 py-0.5 text-xs rounded-full bg-indaco/10 text-indaco">
                        {listini.find(l => l.id === c.listino_id)?.nome || "—"}
                      </span>
                    ) : <span className="text-xs text-slate-400">—</span>}
                  </td>
                  <td>
                    <div className="flex gap-1">
                      <button onClick={() => openProfile(c)} className="p-1.5 hover:bg-indaco/10 rounded" title="Profilo" data-testid={`profile-${c.id}`}><Eye size={16} className="text-indaco" /></button>
                      <button onClick={() => edit(c)} className="p-1.5 hover:bg-slate-100 rounded" data-testid={`edit-${c.id}`}><PencilSimple size={16} className="text-slate-500" /></button>
                      <button onClick={() => del(c.id)} className="p-1.5 hover:bg-red-50 rounded" data-testid={`del-${c.id}`}><Trash size={16} className="text-red-500" /></button>
                    </div>
                  </td>
                </tr>
              ))}
              {list.length === 0 && <tr><td colSpan={5} className="text-center py-12 text-slate-400">Nessun cliente trovato</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {/* Profile drawer */}
      <Dialog open={!!profile} onOpenChange={(o) => { if (!o) setProfile(null); }}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto" data-testid="cliente-profile">
          {profile && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-3">
                  <Buildings size={24} className="text-indaco" weight="duotone" />
                  <div>
                    <div>{profile.cliente.ragione_sociale}</div>
                    <div className="text-xs font-mono uppercase tracking-wider text-slate-500 mt-0.5">
                      {profile.cliente.denominazione_struttura || profile.cliente.tipologia}
                      {profile.listino && <> · Listino <b className="text-indaco">{profile.listino.nome}</b></>}
                    </div>
                  </div>
                </DialogTitle>
              </DialogHeader>

              {/* KPI */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 my-4">
                <div className="kpi-card !p-3"><div className="overline">DDT totali</div><div className="font-display text-2xl font-bold">{profile.stats.ddt_totali}</div><div className="text-[11px] text-amber-600">{profile.stats.ddt_non_fatturati} non fatt.</div></div>
                <div className="kpi-card !p-3"><div className="overline">Fatturato</div><div className="font-display text-2xl font-bold text-indaco">€ {profile.stats.fatturato_totale.toFixed(2)}</div></div>
                <div className="kpi-card !p-3"><div className="overline">Incassato</div><div className="font-display text-2xl font-bold text-emerald-600">€ {profile.stats.incassato_totale.toFixed(2)}</div></div>
                <div className="kpi-card !p-3"><div className="overline">Sospeso</div><div className="font-display text-2xl font-bold text-amber-600">€ {profile.stats.sospeso_totale.toFixed(2)}</div></div>
              </div>

              {/* Portale pubblico link */}
              <div className="mb-4 p-3 rounded-lg border border-indaco/20 bg-indaco/5" data-testid="cliente-portale-panel">
                <div className="flex items-start gap-3">
                  <LinkIcon size={18} className="text-indaco flex-shrink-0 mt-0.5" weight="duotone" />
                  <div className="flex-1 min-w-0">
                    <div className="font-display font-bold text-sm text-indaco">Portale cliente</div>
                    <div className="text-[11px] text-slate-600 mt-0.5">
                      Il cliente può accedere autonomamente al portale self-service inserendo la propria P.IVA / Codice Fiscale:
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                      <code className="flex-1 px-2 py-1 bg-white border border-slate-200 rounded text-[11px] font-mono truncate">
                        {window.location.origin}/portale
                      </code>
                      <Button type="button" size="sm" variant="outline"
                        onClick={() => { navigator.clipboard.writeText(`${window.location.origin}/portale`); toast.success("Copiato"); }}
                        data-testid="copy-portale-selfservice"><Copy size={13} /></Button>
                      <Button type="button" size="sm" variant="outline" onClick={() => inviaLinkEmail("self_service")}
                        title={profile.cliente?.email ? `Invia a ${profile.cliente.email}` : "Email cliente mancante"}
                        disabled={!profile.cliente?.email}
                        data-testid="send-portale-selfservice-email">
                        <EnvelopeSimple size={13} className="mr-1" />Email
                      </Button>
                    </div>
                    <div className="text-[11px] text-slate-400 mt-2 pt-2 border-t border-indaco/10">
                      In alternativa, link diretto con token statico (utile per QR code o email):
                    </div>
                    {profile.cliente.portale_token ? (
                      <div className="mt-1 flex items-center gap-2">
                        <code className="flex-1 px-2 py-1 bg-white border border-slate-200 rounded text-[11px] font-mono truncate">
                          {window.location.origin}/ordina/{profile.cliente.portale_token}
                        </code>
                        <Button type="button" size="sm" variant="outline" onClick={copiaLink} data-testid="copy-portale-link"><Copy size={13} /></Button>
                        <Button type="button" size="sm" variant="outline" onClick={() => inviaLinkEmail("diretto")}
                          title={profile.cliente?.email ? `Invia a ${profile.cliente.email}` : "Email cliente mancante"}
                          disabled={!profile.cliente?.email}
                          data-testid="send-portale-diretto-email">
                          <EnvelopeSimple size={13} className="mr-1" />Email
                        </Button>
                        <Button type="button" size="sm" variant="outline" onClick={revocaPortale} className="text-red-600" data-testid="revoke-portale-link"><Prohibit size={13} /></Button>
                      </div>
                    ) : (
                      <div className="mt-1 flex gap-2">
                        <Button type="button" size="sm" variant="outline" onClick={generaPortale} data-testid="generate-portale-link">
                          <LinkIcon size={13} className="mr-1" />Genera link diretto
                        </Button>
                        <Button type="button" size="sm" variant="outline" onClick={() => inviaLinkEmail("diretto")}
                          title={profile.cliente?.email ? `Genera e invia a ${profile.cliente.email}` : "Email cliente mancante"}
                          disabled={!profile.cliente?.email}
                          data-testid="send-portale-diretto-email">
                          <EnvelopeSimple size={13} className="mr-1" />Genera & invia
                        </Button>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Fatture */}
              <div>
                <h4 className="font-display font-bold text-sm mb-2 flex items-center gap-2"><Receipt size={16} className="text-indaco" weight="duotone" />Storico fatture ({profile.fatture.length})</h4>
                <div className="kpi-card p-0 overflow-x-auto max-h-64 overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead className="text-xs uppercase tracking-widest text-slate-500 border-b border-slate-200 sticky top-0 bg-white">
                      <tr><th className="text-left py-2 px-3">Numero</th><th>Data</th><th className="text-right">Totale</th><th className="text-center">Stato</th><th></th></tr>
                    </thead>
                    <tbody>
                      {profile.fatture.map(f => (
                        <tr key={f.id} className="border-b border-slate-100">
                          <td className="py-2 px-3 font-mono font-bold">{f.numero}</td>
                          <td className="text-xs">{new Date(f.data).toLocaleDateString("it-IT")}</td>
                          <td className="text-right font-mono font-bold">€ {f.totale.toFixed(2)}</td>
                          <td className="text-center">
                            {f.stato_incasso === "incassata" ? (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] rounded-full bg-emerald-100 text-emerald-700"><CheckCircle size={10} weight="fill" /> Incassata</span>
                            ) : (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] rounded-full bg-amber-100 text-amber-700"><CurrencyEur size={10} /> Da incassare</span>
                            )}
                          </td>
                          <td className="text-right pr-3">
                            <button onClick={() => openPdf("fatture", f.id)} className="text-xs text-indaco hover:underline">PDF</button>
                          </td>
                        </tr>
                      ))}
                      {profile.fatture.length === 0 && <tr><td colSpan={5} className="text-center py-6 text-slate-400 text-sm">Nessuna fattura</td></tr>}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* DDT recenti */}
              <div className="mt-4">
                <h4 className="font-display font-bold text-sm mb-2 flex items-center gap-2"><Truck size={16} className="text-indaco" weight="duotone" />D.D.T. ({profile.ddts.length})</h4>
                <div className="kpi-card p-0 overflow-x-auto max-h-64 overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead className="text-xs uppercase tracking-widest text-slate-500 border-b border-slate-200 sticky top-0 bg-white">
                      <tr><th className="text-left py-2 px-3">Numero</th><th>Data</th><th className="text-right">Imponibile</th><th className="text-center">Fatturazione</th><th></th></tr>
                    </thead>
                    <tbody>
                      {profile.ddts.map(d => (
                        <tr key={d.id} className="border-b border-slate-100">
                          <td className="py-2 px-3 font-mono font-bold">{d.numero}</td>
                          <td className="text-xs">{new Date(d.data).toLocaleDateString("it-IT")}</td>
                          <td className="text-right font-mono">€ {d.imponibile.toFixed(2)}</td>
                          <td className="text-center text-[11px]">
                            {d.stato_fatturazione === "fatturato" ? <span className="text-emerald-600">✓ {d.fattura_numero}</span> : <span className="text-amber-600">Non fatt.</span>}
                          </td>
                          <td className="text-right pr-3">
                            <button onClick={() => openPdf("ddt", d.id)} className="text-xs text-indaco hover:underline">PDF</button>
                          </td>
                        </tr>
                      ))}
                      {profile.ddts.length === 0 && <tr><td colSpan={5} className="text-center py-6 text-slate-400 text-sm">Nessun DDT</td></tr>}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
