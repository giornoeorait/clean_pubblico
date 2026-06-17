import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Plus, User, ShieldCheck, Trash, CheckCircle, XCircle, CalendarBlank } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function Utenti() {
  const [users, setUsers] = useState([]);
  const [audit, setAudit] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ email: "", password: "", name: "", role: "contabilita", can_edit_dates: false });
  const [meId, setMeId] = useState(null);

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
    </div>
  );
}
