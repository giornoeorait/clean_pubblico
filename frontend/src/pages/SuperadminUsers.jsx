import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Plus, Crown, Trash, PencilSimple, CheckCircle, XCircle } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function SuperadminUsers() {
  const [list, setList] = useState([]);
  const [me, setMe] = useState(null);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ email: "", password: "", name: "" });

  const fetchAll = async () => {
    const [a, b] = await Promise.all([
      api.get("/admin/superadmins"),
      api.get("/auth/me"),
    ]);
    setList(a.data); setMe(b.data);
  };
  useEffect(() => { fetchAll(); }, []);

  const save = async (e) => {
    e.preventDefault();
    try {
      if (editing) {
        const payload = { name: form.name };
        if (form.password) payload.password = form.password;
        await api.patch(`/admin/superadmins/${editing}`, payload);
        toast.success("Superadmin aggiornato");
      } else {
        await api.post("/admin/superadmins", form);
        toast.success("Superadmin creato");
      }
      setOpen(false); setEditing(null); setForm({ email: "", password: "", name: "" });
      fetchAll();
    } catch (e2) { toast.error(e2.response?.data?.detail || "Errore"); }
  };

  const startEdit = (u) => { setForm({ email: u.email, password: "", name: u.name }); setEditing(u.id); setOpen(true); };

  const toggleAttivo = async (u) => {
    try { await api.patch(`/admin/superadmins/${u.id}`, { attivo: !u.attivo }); toast.success("Stato aggiornato"); fetchAll(); }
    catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  const del = async (u) => {
    if (!window.confirm(`Eliminare definitivamente ${u.name} (${u.email})?`)) return;
    try { await api.delete(`/admin/superadmins/${u.id}`); toast.success("Eliminato"); fetchAll(); }
    catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Superadmin · cross-tenant"
        title="Gestione superadmin"
        subtitle="Lista degli account con accesso a tutte le funzioni di amministrazione SaaS. Visibile solo ai superadmin."
        actions={
          <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setEditing(null); setForm({ email: "", password: "", name: "" }); } }}>
            <DialogTrigger asChild>
              <Button className="bg-indaco hover:bg-indaco-dark" data-testid="new-superadmin-btn"><Plus size={16} className="mr-1" /> Nuovo superadmin</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>{editing ? "Modifica superadmin" : "Nuovo superadmin"}</DialogTitle>
                <DialogDescription>{editing ? "Modifica nome e password. L'email non è modificabile." : "Crea un nuovo account con privilegi cross-tenant."}</DialogDescription>
              </DialogHeader>
              <form onSubmit={save} className="space-y-3">
                <div><Label>Email *</Label><Input type="email" value={form.email} disabled={!!editing} onChange={e => setForm({ ...form, email: e.target.value })} data-testid="super-email" /></div>
                <div><Label>Nome *</Label><Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} data-testid="super-name" /></div>
                <div>
                  <Label>{editing ? "Nuova password (lascia vuoto per mantenere)" : "Password *"}</Label>
                  <Input type="password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} minLength={editing ? 0 : 8} data-testid="super-password" />
                  {!editing && <p className="text-[10px] text-slate-400 mt-1">Minimo 8 caratteri</p>}
                </div>
                <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setOpen(false)}>Annulla</Button><Button type="submit" className="bg-indaco hover:bg-indaco-dark" data-testid="save-super-btn">Salva</Button></div>
              </form>
            </DialogContent>
          </Dialog>
        }
      />

      <div className="kpi-card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead><tr><th>Nome</th><th>Email</th><th>Stato</th><th>Creato</th><th>Azioni</th></tr></thead>
            <tbody>
              {list.map(u => {
                const isMe = u.id === me?.id;
                return (
                  <tr key={u.id} data-testid={`super-row-${u.id}`}>
                    <td>
                      <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-amber-400 to-orange-600 flex items-center justify-center">
                          <Crown size={14} className="text-white" weight="fill" />
                        </div>
                        <span className="font-medium">{u.name}</span>
                        {isMe && <span className="text-[10px] bg-indaco/10 text-indaco rounded px-1.5 py-0.5 font-mono">tu</span>}
                      </div>
                    </td>
                    <td className="font-mono text-xs">{u.email}</td>
                    <td>{u.attivo !== false ? <span className="text-xs text-emerald-600 font-semibold">Attivo</span> : <span className="text-xs text-red-500">Disattivo</span>}</td>
                    <td className="text-xs text-slate-500 font-mono">{u.created_at?.slice(0, 10)}</td>
                    <td>
                      <div className="flex gap-1">
                        <button onClick={() => startEdit(u)} className="p-1.5 hover:bg-slate-100 rounded" title="Modifica" data-testid={`super-edit-${u.id}`}><PencilSimple size={14} /></button>
                        {!isMe && (
                          <>
                            <button onClick={() => toggleAttivo(u)} className="p-1.5 hover:bg-slate-100 rounded" title={u.attivo !== false ? "Disattiva" : "Riattiva"} data-testid={`super-toggle-${u.id}`}>
                              {u.attivo !== false ? <XCircle size={14} className="text-amber-600" /> : <CheckCircle size={14} className="text-emerald-500" />}
                            </button>
                            <button onClick={() => del(u)} className="p-1.5 hover:bg-red-50 rounded" title="Elimina" data-testid={`super-delete-${u.id}`}><Trash size={14} className="text-red-500" /></button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {list.length === 0 && <tr><td colSpan={5} className="text-center py-8 text-slate-400">Nessun superadmin (impossibile — dovresti vedere almeno te stesso!)</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
