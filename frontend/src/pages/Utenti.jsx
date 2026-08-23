import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Plus, User, ShieldCheck, Trash, CheckCircle, XCircle, CalendarBlank, Sliders } from "@phosphor-icons/react";
import { toast } from "sonner";
import { PERMISSION_SECTIONS, SECTION_LABELS, getResolvedPermissions } from "../lib/permissions";

export default function Utenti() {
  const [users, setUsers] = useState([]);
  const [audit, setAudit] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ email: "", password: "", name: "", role: "contabilita", can_edit_dates: false });
  const [meId, setMeId] = useState(null);

  // Dialog permessi granulari
  const [permTarget, setPermTarget] = useState(null); // utente selezionato
  const [permMatrix, setPermMatrix] = useState({});   // { section: {view, edit} }
  const [savingPerm, setSavingPerm] = useState(false);

  const fetch = async () => {
    const [u, a, me] = await Promise.all([
      api.get("/users"),
      api.get("/audit-log?limit=200"),
      api.get("/auth/me"),
    ]);
    setUsers(u.data); setAudit(a.data); setMeId(me.data?.id);
  };
  useEffect(() => { fetch(); }, []);

  const save = async (e) => {
    e.preventDefault();
    try { await api.post("/users", form); toast.success("Utente creato"); setOpen(false); setForm({ email: "", password: "", name: "", role: "contabilita", can_edit_dates: false }); fetch(); }
    catch (e) { toast.error(e.response?.data?.detail); }
  };

  const toggleCanEditDates = async (u) => {
    try {
      const next = !u.can_edit_dates;
      await api.patch(`/users/${u.id}`, { can_edit_dates: next });
      toast.success(next ? `${u.name}: permesso modifica data DDT attivato` : `${u.name}: permesso revocato`);
      fetch();
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const openPermDialog = (u) => {
    setPermTarget(u);
    // Precompila con i permessi risolti (default ruolo + eventuale override)
    setPermMatrix(getResolvedPermissions(u));
  };

  const togglePerm = (section, action) => {
    setPermMatrix(prev => {
      const cur = prev[section] || { view: false, edit: false };
      const next = { ...cur, [action]: !cur[action] };
      // Se disattivo view, disattivo anche edit (edit senza view non ha senso)
      if (action === "view" && !next.view) next.edit = false;
      // Se attivo edit, forzo view=true (edit implica poter vedere)
      if (action === "edit" && next.edit) next.view = true;
      return { ...prev, [section]: next };
    });
  };

  const applyPresetTemplate = (preset) => {
    // preset: "read_only" | "full" | "logistica_std" | "contabilita_std"
    const all = (v, e) => Object.fromEntries(PERMISSION_SECTIONS.map(s => [s, { view: v, edit: e }]));
    if (preset === "read_only")  return setPermMatrix(all(true, false));
    if (preset === "full")       return setPermMatrix(all(true, true));
    if (preset === "logistica_std") return setPermMatrix({
      clienti: { view: true, edit: true },
      articoli: { view: true, edit: true },
      listini: { view: true, edit: false },
      offerte: { view: true, edit: false },
      ordinativi: { view: true, edit: true },
      ddt: { view: true, edit: true },
      ddt_ricevuti: { view: true, edit: true },
      fatture: { view: false, edit: false },
      sospesi: { view: false, edit: false },
      fornitori: { view: false, edit: false },
      fatture_fornitore: { view: false, edit: false },
      costi: { view: false, edit: false },
      dipendenti: { view: false, edit: false },
      report: { view: false, edit: false },
    });
    if (preset === "contabilita_std") return setPermMatrix(all(true, true));
  };

  const savePerms = async () => {
    if (!permTarget) return;
    setSavingPerm(true);
    try {
      await api.patch(`/users/${permTarget.id}`, { permissions: permMatrix });
      toast.success(`Permessi di ${permTarget.name} aggiornati`);
      setPermTarget(null);
      fetch();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore salvataggio permessi");
    } finally {
      setSavingPerm(false);
    }
  };

  const toggleAttivo = async (u) => {
    try {
      if (u.attivo) {
        await api.delete(`/users/${u.id}`);
        toast.success(`${u.name} disattivato`);
      } else {
        await api.patch(`/users/${u.id}/riattiva`);
        toast.success(`${u.name} riattivato`);
      }
      fetch();
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const hardDelete = async (u) => {
    if (!window.confirm(`Eliminare definitivamente ${u.name} (${u.email})? Questa azione è IRREVERSIBILE.`)) return;
    try {
      await api.delete(`/users/${u.id}?hard=true`);
      toast.success(`${u.name} eliminato`);
      fetch();
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Admin"
        title="Utenti & Sicurezza"
        subtitle="Ruoli: admin, logistica, contabilità. Audit log completo di tutte le operazioni."
        actions={
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild><Button className="bg-indaco hover:bg-indaco-dark" data-testid="new-user-btn"><Plus size={16} className="mr-1" />Nuovo Utente</Button></DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Nuovo utente</DialogTitle></DialogHeader>
              <form onSubmit={save} className="space-y-4">
                <div><Label>Nome *</Label><Input required value={form.name} onChange={e => setForm({...form, name: e.target.value})} /></div>
                <div><Label>Email *</Label><Input required type="email" value={form.email} onChange={e => setForm({...form, email: e.target.value})} /></div>
                <div><Label>Password *</Label><Input required type="password" value={form.password} onChange={e => setForm({...form, password: e.target.value})} /></div>
                <div>
                  <Label>Ruolo</Label>
                  <Select value={form.role} onValueChange={v => setForm({...form, role: v})}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="admin">Admin</SelectItem>
                      <SelectItem value="logistica">Logistica</SelectItem>
                      <SelectItem value="contabilita">Contabilità</SelectItem>
                      <SelectItem value="produzione">Produzione (Totem)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="rounded-md border border-slate-200 px-3 py-2.5 bg-slate-50">
                  <label className="flex items-start gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      className="mt-0.5 h-4 w-4 accent-indaco"
                      checked={!!form.can_edit_dates}
                      onChange={e => setForm({...form, can_edit_dates: e.target.checked})}
                      data-testid="new-user-can-edit-dates"
                    />
                    <span className="text-sm">
                      <span className="font-semibold flex items-center gap-1"><CalendarBlank size={14} /> Può modificare la data dei DDT</span>
                      <span className="block text-[11px] text-slate-500">Permette all'utente (anche se non admin) di cambiare la data di un DDT non fatturato.</span>
                    </span>
                  </label>
                </div>
                <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setOpen(false)}>Annulla</Button><Button type="submit" className="bg-indaco hover:bg-indaco-dark">Crea</Button></div>
              </form>
            </DialogContent>
          </Dialog>
        }
      />

      <Tabs defaultValue="users">
        <TabsList>
          <TabsTrigger value="users" data-testid="tab-users"><User size={14} className="mr-1" />Utenti ({users.length})</TabsTrigger>
          <TabsTrigger value="audit" data-testid="tab-audit"><ShieldCheck size={14} className="mr-1" />Audit Log</TabsTrigger>
        </TabsList>

        <TabsContent value="users" className="mt-4">
          <div className="kpi-card p-0 overflow-hidden">
            <table className="data-table">
              <thead><tr><th>Utente</th><th>Email</th><th>Ruolo</th><th>Permessi</th><th>Stato</th><th>Creato</th><th>Azioni</th></tr></thead>
              <tbody>
                {users.map(u => {
                  const isMe = u.id === meId;
                  const isAdmin = u.role === "admin";
                  const hasEditDates = isAdmin || !!u.can_edit_dates;
                  return (
                    <tr key={u.id} data-testid={`user-row-${u.id}`}>
                      <td className="flex items-center gap-2 py-3">
                        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-celeste to-indaco text-white flex items-center justify-center text-xs font-bold">{u.name?.[0]?.toUpperCase()}</div>
                        <span className="font-medium">{u.name}</span>
                        {isMe && <span className="text-[10px] bg-indaco/10 text-indaco rounded px-1.5 py-0.5 font-mono">tu</span>}
                      </td>
                      <td className="font-mono text-xs">{u.email}</td>
                      <td><span className="text-xs uppercase tracking-wider font-semibold text-indaco">{u.role}</span></td>
                      <td>
                        <button
                          onClick={() => !isAdmin && toggleCanEditDates(u)}
                          disabled={isAdmin}
                          title={isAdmin ? "Gli admin hanno automaticamente tutti i permessi" : (hasEditDates ? "Revoca permesso modifica data DDT" : "Concedi permesso modifica data DDT")}
                          className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-[11px] font-medium transition-colors ${
                            hasEditDates
                              ? "bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                              : "bg-slate-50 text-slate-500 hover:bg-slate-100"
                          } ${isAdmin ? "cursor-default opacity-90" : "cursor-pointer"}`}
                          data-testid={`user-toggle-can-edit-dates-${u.id}`}
                        >
                          <CalendarBlank size={12} weight={hasEditDates ? "fill" : "regular"} />
                          {hasEditDates ? "Modifica data DDT" : "No modifica date"}
                        </button>
                      </td>
                      <td>{u.attivo ? <span className="text-xs text-emerald-600 font-semibold">Attivo</span> : <span className="text-xs text-red-500">Disattivo</span>}</td>
                      <td className="text-xs text-slate-500 font-mono">{u.created_at?.slice(0, 10)}</td>
                      <td>
                        {isMe ? (
                          <span className="text-[11px] text-slate-400 italic">—</span>
                        ) : (
                          <div className="flex gap-1">
                            {!isAdmin && (
                              <button
                                onClick={() => openPermDialog(u)}
                                className="p-1.5 hover:bg-indaco/10 rounded"
                                title="Configura permessi (cosa può vedere/modificare)"
                                data-testid={`user-perms-${u.id}`}>
                                <Sliders size={16} className="text-indaco" />
                              </button>
                            )}
                            <button
                              onClick={() => toggleAttivo(u)}
                              className="p-1.5 hover:bg-slate-100 rounded"
                              title={u.attivo ? "Disattiva (soft-delete)" : "Riattiva"}
                              data-testid={`user-toggle-${u.id}`}>
                              {u.attivo
                                ? <XCircle size={16} className="text-amber-600" />
                                : <CheckCircle size={16} className="text-emerald-500" />}
                            </button>
                            <button
                              onClick={() => hardDelete(u)}
                              className="p-1.5 hover:bg-red-50 rounded"
                              title="Elimina definitivamente"
                              data-testid={`user-delete-${u.id}`}>
                              <Trash size={16} className="text-red-500" />
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </TabsContent>

        <TabsContent value="audit" className="mt-4">
          <div className="kpi-card p-0 overflow-hidden">
            <table className="data-table">
              <thead><tr><th>Timestamp</th><th>Utente</th><th>Azione</th><th>Entità</th><th>ID</th></tr></thead>
              <tbody>
                {audit.map(a => (
                  <tr key={a.id}>
                    <td className="text-xs font-mono text-slate-500">{new Date(a.timestamp).toLocaleString("it-IT")}</td>
                    <td className="text-xs">{a.user_email}</td>
                    <td><span className={`text-xs font-bold uppercase tracking-wider ${a.azione === "DELETE" || a.azione === "DEACTIVATE" ? "text-red-600" : a.azione === "CREATE" ? "text-emerald-600" : "text-indaco"}`}>{a.azione}</span></td>
                    <td className="text-xs">{a.entita}</td>
                    <td className="font-mono text-[10px] text-slate-400">{a.entita_id?.slice(0, 8)}…</td>
                  </tr>
                ))}
                {audit.length === 0 && <tr><td colSpan={5} className="text-center py-8 text-slate-400 text-sm">Nessuna attività</td></tr>}
              </tbody>
            </table>
          </div>
        </TabsContent>
      </Tabs>

      {/* Dialog matrice permessi granulari */}
      <Dialog open={!!permTarget} onOpenChange={(o) => { if (!o) setPermTarget(null); }}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="perms-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Sliders size={18} className="text-indaco" />
              Permessi di <span className="text-indaco">{permTarget?.name}</span>
              <span className="text-xs text-slate-500 uppercase tracking-widest font-mono">({permTarget?.role})</span>
            </DialogTitle>
          </DialogHeader>
          {permTarget && (
            <div className="space-y-4">
              <div className="rounded-md bg-slate-50 border border-slate-200 px-3 py-2 text-xs text-slate-600">
                Per ciascuna sezione decidi se l&apos;utente può <b>Vedere</b> il contenuto e/o <b>Modificarlo</b> (creare/modificare/eliminare).
                Se <i>Modifica</i> è attivo, <i>Vede</i> viene forzato a <b>ON</b>.
              </div>

              {/* Preset rapidi */}
              <div className="flex flex-wrap gap-2">
                <span className="text-xs uppercase tracking-widest text-slate-500 self-center mr-1">Preset:</span>
                <Button variant="outline" size="sm" onClick={() => applyPresetTemplate("read_only")} data-testid="preset-readonly">Solo lettura</Button>
                <Button variant="outline" size="sm" onClick={() => applyPresetTemplate("full")} data-testid="preset-full">Tutto attivo</Button>
                <Button variant="outline" size="sm" onClick={() => applyPresetTemplate("logistica_std")} data-testid="preset-logistica">Logistica standard</Button>
                <Button variant="outline" size="sm" onClick={() => applyPresetTemplate("contabilita_std")} data-testid="preset-contab">Contabilità standard</Button>
              </div>

              {/* Matrice */}
              <div className="rounded-lg border border-slate-200 overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-slate-500 uppercase tracking-widest text-[10px]">
                    <tr>
                      <th className="text-left px-4 py-2">Sezione</th>
                      <th className="text-center px-2 py-2 w-24">Vede</th>
                      <th className="text-center px-2 py-2 w-24">Modifica</th>
                    </tr>
                  </thead>
                  <tbody>
                    {PERMISSION_SECTIONS.map(s => {
                      const cur = permMatrix[s] || { view: false, edit: false };
                      return (
                        <tr key={s} className="border-t border-slate-100 hover:bg-slate-50/50">
                          <td className="px-4 py-2 font-medium">{SECTION_LABELS[s]}</td>
                          <td className="text-center py-2">
                            <input
                              type="checkbox"
                              className="h-4 w-4 accent-indaco cursor-pointer"
                              checked={!!cur.view}
                              onChange={() => togglePerm(s, "view")}
                              data-testid={`perm-${s}-view`}
                            />
                          </td>
                          <td className="text-center py-2">
                            <input
                              type="checkbox"
                              className="h-4 w-4 accent-indaco cursor-pointer"
                              checked={!!cur.edit}
                              onChange={() => togglePerm(s, "edit")}
                              data-testid={`perm-${s}-edit`}
                            />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-200">
                <Button variant="outline" onClick={() => setPermTarget(null)}>Annulla</Button>
                <Button className="bg-indaco hover:bg-indaco-dark" onClick={savePerms} disabled={savingPerm} data-testid="perms-save">
                  {savingPerm ? "Salvataggio…" : "Salva permessi"}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
