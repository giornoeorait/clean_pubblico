import React, { useEffect, useState, useMemo } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Plus, Wallet, Trash, PencilSimple, User, Truck, Lightning, Package, Warning } from "@phosphor-icons/react";
import { toast } from "sonner";

const CATEGORIE = [
  { v: "personale", l: "Personale", icon: User, color: "violet", bg: "bg-violet-100", txt: "text-violet-700" },
  { v: "automezzi", l: "Automezzi", icon: Truck, color: "amber", bg: "bg-amber-100", txt: "text-amber-700" },
  { v: "utenze", l: "Utenze", icon: Lightning, color: "sky", bg: "bg-sky-100", txt: "text-sky-700" },
  { v: "prodotti", l: "Prodotti", icon: Package, color: "emerald", bg: "bg-emerald-100", txt: "text-emerald-700" },
];

const TIPI_RAPPORTO = ["stipendio", "contributi", "tfr", "trasferta", "straordinario", "altro"];
const TIPI_AUTO = ["carburante", "manutenzione", "assicurazione", "bollo", "revisione", "altro"];
const TIPI_UTENZA = ["gas", "luce", "acqua", "telefono", "internet", "altro"];

const emptyFor = (cat) => ({
  categoria: cat,
  data: new Date().toISOString().slice(0, 10),
  mese_riferimento: new Date().toISOString().slice(0, 7),
  descrizione: "",
  importo: 0,
  fornitore_id: "",
  dipendente_nome: "",
  ore_lavorate: "",
  tipo_rapporto: "stipendio",
  automezzo_targa: "",
  automezzo_km: "",
  tipo_automezzo_costo: "carburante",
  tipo_utenza: "luce",
  consumo: "",
  unita_consumo: "kWh",
  articolo_codice: "",
  quantita: "",
  note: "",
});

function monthsOfYear(anno) {
  return Array.from({ length: 12 }, (_, i) => `${anno}-${String(i + 1).padStart(2, "0")}`);
}

export default function Costi() {
  const [tab, setTab] = useState("personale");
  const [list, setList] = useState([]);
  const [summary, setSummary] = useState(null);
  const [fornitori, setFornitori] = useState([]);
  const [dipendenti, setDipendenti] = useState([]);
  const [automezzi, setAutomezzi] = useState([]);
  const [anno, setAnno] = useState(new Date().getFullYear());
  const [meseFiltro, setMeseFiltro] = useState("all");
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyFor("personale"));

  const activeCat = CATEGORIE.find(c => c.v === tab);

  const fetchData = async () => {
    const params = [`categoria=${tab}`];
    if (meseFiltro !== "all") params.push(`mese_riferimento=${meseFiltro}`);
    else params.push(`anno=${anno}`);
    const [a, b, c, d, e] = await Promise.all([
      api.get(`/costi?${params.join("&")}`),
      api.get(`/costi/summary?anno=${anno}`),
      api.get("/fornitori"),
      api.get("/dipendenti?attivo=true").catch(() => ({ data: [] })),
      api.get("/automezzi?attivo=true").catch(() => ({ data: [] })),
    ]);
    setList(a.data); setSummary(b.data); setFornitori(c.data);
    setDipendenti(d.data); setAutomezzi(e.data);
  };
  useEffect(() => { fetchData(); }, [tab, anno, meseFiltro]);

  const resetForm = () => setForm(emptyFor(tab));

  const save = async (e) => {
    e.preventDefault();
    if (!form.descrizione || !form.importo || form.importo <= 0) {
      toast.error("Compila descrizione e importo > 0"); return;
    }
    try {
      // Pulisci numerici
      const payload = { ...form };
      ["ore_lavorate", "automezzo_km", "consumo", "quantita"].forEach(k => {
        payload[k] = payload[k] === "" || payload[k] === null ? null : Number(payload[k]);
      });
      payload.importo = Number(payload.importo);
      if (!payload.fornitore_id) payload.fornitore_id = null;
      // Rimuovi campi non pertinenti ad altre categorie (opzionale per pulizia)
      if (editing) { await api.patch(`/costi/${editing}`, payload); toast.success("Costo aggiornato"); }
      else { await api.post("/costi", payload); toast.success("Costo registrato"); }
      setOpen(false); setEditing(null); resetForm(); fetchData();
    } catch (e2) { toast.error(e2.response?.data?.detail || "Errore"); }
  };

  const edit = (c) => {
    setForm({ ...emptyFor(c.categoria), ...c, fornitore_id: c.fornitore_id || "", ore_lavorate: c.ore_lavorate ?? "", automezzo_km: c.automezzo_km ?? "", consumo: c.consumo ?? "", quantita: c.quantita ?? "" });
    setEditing(c.id); setTab(c.categoria); setOpen(true);
  };
  const del = async (id) => {
    if (!window.confirm("Eliminare costo?")) return;
    try { await api.delete(`/costi/${id}`); toast.success("Eliminato"); fetchData(); }
    catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const totaleCategoria = useMemo(() => list.reduce((s, c) => s + (c.importo || 0), 0), [list]);
  const mesi = useMemo(() => monthsOfYear(anno), [anno]);

  return (
    <div>
      <PageHeader
        eyebrow="Controllo di gestione"
        title="Costi"
        subtitle="Imputazione mensile dei costi aziendali per categoria. Base per i report di marginalità e costo/kg."
        actions={
          <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (o && !editing) setForm(emptyFor(tab)); if (!o) { setEditing(null); resetForm(); } }}>
            <DialogTrigger asChild>
              <Button className="bg-indaco hover:bg-indaco-dark" data-testid="new-costo-btn"><Plus size={16} weight="bold" className="mr-1" /> Nuovo costo</Button>
            </DialogTrigger>
            <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
              <DialogHeader><DialogTitle>{editing ? "Modifica costo" : "Registra nuovo costo"}</DialogTitle><DialogDescription>Seleziona la categoria in alto, compila i campi comuni (data/mese/importo) e i campi specifici della categoria.</DialogDescription></DialogHeader>
              <form onSubmit={save} className="space-y-4">
                {/* Selettore categoria */}
                <div className="grid grid-cols-4 gap-2">
                  {CATEGORIE.map(c => {
                    const Icon = c.icon;
                    return (
                      <button key={c.v} type="button" disabled={!!editing}
                        onClick={() => setForm({ ...emptyFor(c.v), data: form.data, mese_riferimento: form.mese_riferimento, descrizione: form.descrizione, importo: form.importo })}
                        className={`border rounded-lg p-3 flex flex-col items-center gap-1 text-xs transition ${form.categoria === c.v ? "border-indaco bg-indaco/5 text-indaco font-bold" : "border-slate-200 hover:border-slate-300"}`}>
                        <Icon size={18} />
                        {c.l}
                      </button>
                    );
                  })}
                </div>

                {/* Campi comuni */}
                <div className="grid grid-cols-3 gap-3">
                  <div><Label>Data *</Label><Input type="date" value={form.data} onChange={e => setForm({ ...form, data: e.target.value })} data-testid="costo-data" /></div>
                  <div>
                    <Label>Mese di competenza *</Label>
                    <Select value={form.mese_riferimento} onValueChange={v => setForm({ ...form, mese_riferimento: v })}>
                      <SelectTrigger data-testid="costo-mese"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {[anno - 1, anno, anno + 1].flatMap(y => monthsOfYear(y)).map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div><Label>Importo € *</Label><Input type="number" step="0.01" value={form.importo} onChange={e => setForm({ ...form, importo: e.target.value })} data-testid="costo-importo" /></div>
                  <div className="col-span-3"><Label>Descrizione *</Label><Input value={form.descrizione} onChange={e => setForm({ ...form, descrizione: e.target.value })} data-testid="costo-descrizione" /></div>
                </div>

                {/* Campi specifici PER CATEGORIA */}
                {form.categoria === "personale" && (
                  <div className="border rounded p-3 bg-violet-50/40">
                    <div className="grid grid-cols-3 gap-3">
                      <div className="col-span-2">
                        <Label>Dipendente</Label>
                        {dipendenti.length > 0 ? (
                          <Select value={form.dipendente_nome || "libero"} onValueChange={v => {
                            if (v === "libero") { setForm({ ...form, dipendente_nome: "" }); return; }
                            const d = dipendenti.find(x => x.nome === v);
                            setForm({ ...form, dipendente_nome: v, ore_lavorate: form.ore_lavorate || d?.ore_contrattuali || "" });
                          }}>
                            <SelectTrigger><SelectValue placeholder="— seleziona —" /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="libero">— Nome libero —</SelectItem>
                              {dipendenti.map(d => <SelectItem key={d.id} value={d.nome}>{d.nome}{d.ruolo ? ` · ${d.ruolo}` : ""}</SelectItem>)}
                            </SelectContent>
                          </Select>
                        ) : (
                          <Input value={form.dipendente_nome} onChange={e => setForm({ ...form, dipendente_nome: e.target.value })} placeholder="Nessun dipendente in anagrafica" />
                        )}
                      </div>
                      <div>
                        <Label>Tipo</Label>
                        <Select value={form.tipo_rapporto} onValueChange={v => setForm({ ...form, tipo_rapporto: v })}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>{TIPI_RAPPORTO.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
                        </Select>
                      </div>
                      <div><Label>Ore lavorate (mese)</Label><Input type="number" step="0.5" value={form.ore_lavorate} onChange={e => setForm({ ...form, ore_lavorate: e.target.value })} /></div>
                    </div>
                  </div>
                )}

                {form.categoria === "automezzi" && (
                  <div className="border rounded p-3 bg-amber-50/40">
                    <div className="grid grid-cols-3 gap-3">
                      <div>
                        <Label>Targa</Label>
                        {automezzi.length > 0 ? (
                          <Select value={form.automezzo_targa || "libero"} onValueChange={v => setForm({ ...form, automezzo_targa: v === "libero" ? "" : v })}>
                            <SelectTrigger><SelectValue placeholder="— seleziona —" /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="libero">— Targa libera —</SelectItem>
                              {automezzi.map(a => <SelectItem key={a.id} value={a.targa}>{a.targa}{a.marca_modello ? ` · ${a.marca_modello}` : ""}</SelectItem>)}
                            </SelectContent>
                          </Select>
                        ) : (
                          <Input value={form.automezzo_targa} onChange={e => setForm({ ...form, automezzo_targa: e.target.value })} placeholder="AB123CD" />
                        )}
                      </div>
                      <div>
                        <Label>Tipo costo</Label>
                        <Select value={form.tipo_automezzo_costo} onValueChange={v => setForm({ ...form, tipo_automezzo_costo: v })}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>{TIPI_AUTO.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
                        </Select>
                      </div>
                      <div><Label>Km percorsi</Label><Input type="number" step="0.1" value={form.automezzo_km} onChange={e => setForm({ ...form, automezzo_km: e.target.value })} /></div>
                    </div>
                  </div>
                )}

                {form.categoria === "utenze" && (
                  <div className="border rounded p-3 bg-sky-50/40">
                    <div className="grid grid-cols-3 gap-3">
                      <div>
                        <Label>Tipo utenza</Label>
                        <Select value={form.tipo_utenza} onValueChange={v => setForm({ ...form, tipo_utenza: v })}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>{TIPI_UTENZA.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
                        </Select>
                      </div>
                      <div><Label>Consumo</Label><Input type="number" step="0.01" value={form.consumo} onChange={e => setForm({ ...form, consumo: e.target.value })} /></div>
                      <div><Label>Unità</Label><Input value={form.unita_consumo} onChange={e => setForm({ ...form, unita_consumo: e.target.value })} placeholder="kWh, mc, min" /></div>
                    </div>
                  </div>
                )}

                {form.categoria === "prodotti" && (
                  <div className="border rounded p-3 bg-emerald-50/40">
                    <div className="grid grid-cols-3 gap-3">
                      <div><Label>Codice articolo</Label><Input value={form.articolo_codice} onChange={e => setForm({ ...form, articolo_codice: e.target.value })} placeholder="ART-001" /></div>
                      <div><Label>Quantità</Label><Input type="number" step="0.01" value={form.quantita} onChange={e => setForm({ ...form, quantita: e.target.value })} /></div>
                    </div>
                  </div>
                )}

                {/* Fornitore opzionale (non per personale) */}
                {form.categoria !== "personale" && (
                  <div>
                    <Label>Fornitore (opzionale)</Label>
                    <Select value={form.fornitore_id || "none"} onValueChange={v => setForm({ ...form, fornitore_id: v === "none" ? "" : v })}>
                      <SelectTrigger><SelectValue placeholder="Nessuno" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">— Nessuno —</SelectItem>
                        {fornitori.map(f => <SelectItem key={f.id} value={f.id}>{f.ragione_sociale}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                )}

                <div><Label>Note</Label><Input value={form.note} onChange={e => setForm({ ...form, note: e.target.value })} /></div>

                <div className="flex justify-end gap-2">
                  <Button type="button" variant="outline" onClick={() => setOpen(false)}>Annulla</Button>
                  <Button type="submit" className="bg-indaco hover:bg-indaco-dark" data-testid="save-costo-btn">Salva costo</Button>
                </div>
              </form>
            </DialogContent>
          </Dialog>
        }
      />

      {/* KPI Summary per categoria (anno) */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          {CATEGORIE.map(c => {
            const Icon = c.icon;
            const stat = summary.per_categoria[c.v] || { totale: 0, n: 0 };
            return (
              <button key={c.v} onClick={() => setTab(c.v)}
                className={`kpi-card p-4 text-left transition ${tab === c.v ? "ring-2 ring-indaco" : ""}`}
                data-testid={`costo-tab-${c.v}`}>
                <div className="flex items-center gap-2 mb-1">
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${c.bg}`}>
                    <Icon size={16} className={c.txt} weight="duotone" />
                  </div>
                  <div className="text-[11px] uppercase tracking-wide text-slate-500 font-mono">{c.l}</div>
                </div>
                <div className="text-2xl font-display font-bold text-slate-900">€ {stat.totale.toFixed(2)}</div>
                <div className="text-[11px] text-slate-400">{stat.n} voci · {anno}</div>
              </button>
            );
          })}
        </div>
      )}

      {/* Totale generale */}
      {summary && (
        <div className="kpi-card mb-6 flex items-center justify-between p-4 bg-gradient-to-r from-indaco/5 to-celeste/5 border-indaco/20">
          <div className="flex items-center gap-3">
            <Wallet size={24} className="text-indaco" weight="duotone" />
            <div>
              <div className="text-[11px] uppercase tracking-wide text-slate-500 font-mono">Totale costi {anno}</div>
              <div className="text-3xl font-display font-bold text-indaco">€ {summary.totale_generale.toFixed(2)}</div>
            </div>
          </div>
          <div className="flex gap-2">
            <Select value={String(anno)} onValueChange={v => setAnno(Number(v))}>
              <SelectTrigger className="w-28" data-testid="anno-selector"><SelectValue /></SelectTrigger>
              <SelectContent>
                {[anno - 2, anno - 1, anno, anno + 1].map(y => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={meseFiltro} onValueChange={setMeseFiltro}>
              <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Tutto l'anno</SelectItem>
                {mesi.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
      )}

      {/* Trend mensile (bar ascii-style semplice) */}
      {summary && summary.per_mese.length > 0 && (
        <div className="kpi-card mb-6 p-4">
          <h4 className="font-display font-bold text-sm mb-3">Andamento mensile {anno}</h4>
          <div className="flex items-end gap-2 h-32">
            {mesi.map(m => {
              const rec = summary.per_mese.find(x => x.mese === m);
              const max = Math.max(...summary.per_mese.map(x => x.totale), 1);
              const h = rec ? (rec.totale / max) * 100 : 0;
              return (
                <div key={m} className="flex-1 flex flex-col items-center gap-1" title={rec ? `${m}: €${rec.totale.toFixed(2)}` : `${m}: —`}>
                  <div className="w-full bg-slate-100 rounded-t flex items-end" style={{ height: "100px" }}>
                    <div className={`w-full rounded-t ${rec ? "bg-indaco" : ""}`} style={{ height: `${h}%`, minHeight: rec ? "4px" : 0 }} />
                  </div>
                  <div className="text-[10px] font-mono text-slate-500">{m.slice(5)}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-200 mb-4 overflow-x-auto">
        {CATEGORIE.map(c => {
          const Icon = c.icon;
          return (
            <button key={c.v} onClick={() => setTab(c.v)}
              className={`px-4 py-2 text-sm font-medium flex items-center gap-2 border-b-2 transition ${tab === c.v ? "border-indaco text-indaco" : "border-transparent text-slate-500 hover:text-slate-700"}`}>
              <Icon size={16} />{c.l}
            </button>
          );
        })}
      </div>

      {/* Tabella voci categoria */}
      <div className="kpi-card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Data</th>
                <th>Mese</th>
                <th>Descrizione</th>
                {tab === "personale" && <><th>Dipendente</th><th>Tipo</th><th>Ore</th></>}
                {tab === "automezzi" && <><th>Targa</th><th>Tipo</th><th>Km</th></>}
                {tab === "utenze" && <><th>Tipo</th><th>Consumo</th><th>Fornitore</th></>}
                {tab === "prodotti" && <><th>Codice</th><th>Qtà</th><th>Fornitore</th></>}
                <th className="text-right">Importo</th>
                <th>Azioni</th>
              </tr>
            </thead>
            <tbody>
              {list.map(c => {
                const forn = fornitori.find(f => f.id === c.fornitore_id);
                return (
                  <tr key={c.id} data-testid={`costo-row-${c.id}`}>
                    <td className="text-xs font-mono">{c.data}</td>
                    <td className="text-xs"><span className={`px-2 py-0.5 rounded-full text-[11px] ${activeCat.bg} ${activeCat.txt}`}>{c.mese_riferimento}</span></td>
                    <td>{c.descrizione}</td>
                    {tab === "personale" && <><td>{c.dipendente_nome || "—"}</td><td className="text-xs">{c.tipo_rapporto || "—"}</td><td className="text-xs">{c.ore_lavorate ?? "—"}</td></>}
                    {tab === "automezzi" && <><td className="font-mono text-xs">{c.automezzo_targa || "—"}</td><td className="text-xs">{c.tipo_automezzo_costo || "—"}</td><td className="text-xs">{c.automezzo_km ?? "—"}</td></>}
                    {tab === "utenze" && <><td className="text-xs">{c.tipo_utenza || "—"}</td><td className="text-xs">{c.consumo ? `${c.consumo} ${c.unita_consumo || ""}` : "—"}</td><td className="text-xs">{forn?.ragione_sociale || "—"}</td></>}
                    {tab === "prodotti" && <><td className="font-mono text-xs">{c.articolo_codice || "—"}</td><td className="text-xs">{c.quantita ?? "—"}</td><td className="text-xs">{forn?.ragione_sociale || "—"}</td></>}
                    <td className="text-right font-mono font-bold">€ {c.importo.toFixed(2)}</td>
                    <td>
                      <div className="flex gap-1">
                        <button onClick={() => edit(c)} className="p-1.5 hover:bg-slate-100 rounded" data-testid={`costo-edit-${c.id}`}><PencilSimple size={14} /></button>
                        <button onClick={() => del(c.id)} className="p-1.5 hover:bg-red-50 rounded" data-testid={`costo-del-${c.id}`}><Trash size={14} className="text-red-500" /></button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {list.length === 0 && (
                <tr><td colSpan={10} className="text-center py-8 text-slate-400">
                  <Warning size={24} className="mx-auto mb-2 text-slate-300" />
                  Nessun costo registrato per {activeCat.l.toLowerCase()}{meseFiltro !== "all" ? ` nel mese ${meseFiltro}` : ` nell'anno ${anno}`}.
                </td></tr>
              )}
            </tbody>
            {list.length > 0 && (
              <tfoot>
                <tr className="bg-slate-50 font-bold">
                  <td colSpan={tab === "personale" ? 6 : tab === "automezzi" || tab === "utenze" || tab === "prodotti" ? 6 : 3}>Totale {activeCat.l}</td>
                  <td className="text-right font-mono text-indaco">€ {totaleCategoria.toFixed(2)}</td>
                  <td></td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      </div>
    </div>
  );
}
