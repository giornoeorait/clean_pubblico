import React, { useState, useEffect } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Sparkle, ArrowRight, Buildings, User, Lock } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { toast } from "sonner";

export default function Register() {
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const [sp] = useSearchParams();
  const planFromUrl = sp.get("plan") || "pro";
  const cycle = sp.get("cycle") || "monthly";

  const [form, setForm] = useState({
    nome_azienda: "",
    partita_iva: "",
    email: "",
    password: "",
    confirm: "",
    nome_admin: "",
    piano: planFromUrl,
  });
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (form.password.length < 8) { toast.error("Password minimo 8 caratteri"); return; }
    if (form.password !== form.confirm) { toast.error("Le password non corrispondono"); return; }
    setLoading(true);
    try {
      const { data } = await api.post("/tenants/register", {
        nome_azienda: form.nome_azienda.trim(),
        partita_iva: form.partita_iva.trim(),
        email: form.email.trim(),
        password: form.password,
        nome_admin: form.nome_admin.trim(),
        piano: form.piano,
      });
      localStorage.setItem("cleantec_token", data.token);
      setUser(data.user);
      toast.success(`Benvenuto in CleanTec! Hai ${data.trial_days} giorni di prova.`);
      navigate("/dashboard");
    } catch (e2) {
      toast.error(e2.response?.data?.detail || "Errore registrazione");
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-white">
      {/* Left hero */}
      <div className="relative hidden lg:flex flex-col justify-between p-12 bg-slate-900 text-white overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-indaco via-slate-900 to-slate-900" />
        <div className="absolute inset-0 opacity-20" style={{backgroundImage: "radial-gradient(circle at 20% 30%, rgba(125, 211, 252, 0.4), transparent 50%), radial-gradient(circle at 80% 70%, rgba(139, 92, 246, 0.3), transparent 50%)"}} />
        <div className="relative z-10">
          <Link to="/" className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-white/10 backdrop-blur-sm border border-white/20 flex items-center justify-center">
              <Sparkle size={22} weight="fill" className="text-celeste" />
            </div>
            <div>
              <div className="font-display font-bold text-2xl tracking-tight">CleanTec</div>
              <div className="text-[11px] text-celeste font-mono uppercase tracking-widest">Industrial Laundry OS</div>
            </div>
          </Link>
        </div>
        <div className="relative z-10">
          <div className="overline text-celeste mb-3">INIZIA GRATIS</div>
          <h1 className="font-display text-4xl lg:text-5xl font-bold tracking-tight mb-6">
            14 giorni di prova.<br />Nessuna carta richiesta.
          </h1>
          <ul className="space-y-3 text-slate-300">
            <li className="flex items-center gap-2"><ArrowRight size={16} className="text-celeste" /> Attivazione istantanea</li>
            <li className="flex items-center gap-2"><ArrowRight size={16} className="text-celeste" /> Dati isolati, backup automatico</li>
            <li className="flex items-center gap-2"><ArrowRight size={16} className="text-celeste" /> Cancelli quando vuoi, nessun vincolo</li>
            <li className="flex items-center gap-2"><ArrowRight size={16} className="text-celeste" /> Supporto in italiano</li>
          </ul>
        </div>
        <div className="relative z-10 text-xs text-slate-400 font-mono">© 2026 CleanTec Systems</div>
      </div>

      {/* Right form */}
      <div className="flex items-center justify-center p-8 lg:p-16">
        <form onSubmit={submit} className="w-full max-w-md space-y-5">
          <div>
            <div className="overline text-indaco mb-2">REGISTRAZIONE</div>
            <h2 className="font-display text-3xl font-bold text-slate-900">Crea il tuo account</h2>
            <p className="text-sm text-slate-500 mt-1">Piano selezionato: <span className="font-bold capitalize text-indaco">{form.piano}</span> · {cycle === "annual" ? "annuale" : "mensile"}</p>
          </div>

          <div>
            <Label className="flex items-center gap-1.5"><Buildings size={14} /> Nome azienda *</Label>
            <Input required value={form.nome_azienda} onChange={e => setForm({...form, nome_azienda: e.target.value})} placeholder="Lavanderia Rossi Srl" data-testid="reg-nome-azienda" />
          </div>
          <div>
            <Label>Partita IVA (opzionale)</Label>
            <Input value={form.partita_iva} onChange={e => setForm({...form, partita_iva: e.target.value})} placeholder="IT12345678901" data-testid="reg-piva" />
          </div>
          <div>
            <Label className="flex items-center gap-1.5"><User size={14} /> Nome admin *</Label>
            <Input required value={form.nome_admin} onChange={e => setForm({...form, nome_admin: e.target.value})} placeholder="Mario Rossi" data-testid="reg-nome-admin" />
          </div>
          <div>
            <Label>Email *</Label>
            <Input required type="email" value={form.email} onChange={e => setForm({...form, email: e.target.value})} placeholder="mario@lavanderia.it" data-testid="reg-email" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="flex items-center gap-1.5"><Lock size={14} /> Password *</Label>
              <Input required type="password" minLength={8} value={form.password} onChange={e => setForm({...form, password: e.target.value})} data-testid="reg-password" />
            </div>
            <div>
              <Label>Conferma *</Label>
              <Input required type="password" value={form.confirm} onChange={e => setForm({...form, confirm: e.target.value})} data-testid="reg-confirm" />
            </div>
          </div>

          <div className="pt-2">
            <Button type="submit" disabled={loading} className="w-full bg-indaco hover:bg-indaco-dark h-11" data-testid="reg-submit-btn">
              {loading ? "Creazione account…" : "Inizia la prova gratuita"}
            </Button>
            <p className="text-xs text-slate-500 text-center mt-4">
              Hai già un account? <Link to="/login" className="text-indaco font-semibold">Accedi</Link>
            </p>
            <p className="text-[11px] text-slate-400 text-center mt-2">
              Registrandoti accetti i <a href="#" className="underline">Termini di Servizio</a> e la <a href="#" className="underline">Privacy Policy</a>.
            </p>
          </div>
        </form>
      </div>
    </div>
  );
}
