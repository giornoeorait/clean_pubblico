import React, { useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Plus, User, ShieldCheck } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function Utenti() {
  const [users, setUsers] = useState([]);
  const [audit, setAudit] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ email: "", password: "", name: "", role: "contabilita" });

  const fetch = async () => {
    const [u, a] = await Promise.all([api.get("/users"), api.get("/audit-log?limit=200")]);
    setUsers(u.data); setAudit(a.data);
  };
  useEffect(() => { fetch(); }, []);

  const save = async (e) => {
    e.preventDefault();
    try { await api.post("/users", form); toast.success("Utente creato"); setOpen(false); setForm({ email: "", password: "", name: "", role: "contabilita" }); fetch(); }
    catch (e) { toast.error(e.response?.data?.detail); }
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
              <thead><tr><th>Utente</th><th>Email</th><th>Ruolo</th><th>Stato</th><th>Creato</th></tr></thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.id}>
                    <td className="flex items-center gap-2 py-3">
                      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-celeste to-indaco text-white flex items-center justify-center text-xs font-bold">{u.name?.[0]?.toUpperCase()}</div>
                      <span className="font-medium">{u.name}</span>
                    </td>
                    <td className="font-mono text-xs">{u.email}</td>
                    <td><span className="text-xs uppercase tracking-wider font-semibold text-indaco">{u.role}</span></td>
                    <td>{u.attivo ? <span className="text-xs text-emerald-600 font-semibold">Attivo</span> : <span className="text-xs text-red-500">Disattivo</span>}</td>
                    <td className="text-xs text-slate-500 font-mono">{u.created_at?.slice(0, 10)}</td>
                  </tr>
                ))}
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
