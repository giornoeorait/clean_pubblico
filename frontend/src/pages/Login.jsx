import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Sparkle, SignIn, Factory, Truck, ShieldCheck, ChartBar } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function Login() {
  const { login, error } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("admin@cleantec.it");
  const [password, setPassword] = useState("admin123");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    const ok = await login(email, password);
    setLoading(false);
    if (ok) {
      toast.success("Accesso effettuato");
      navigate("/dashboard");
    }
  };

  const quickLogin = (e, pw) => {
    setEmail(e); setPassword(pw);
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-white">
      {/* Left hero */}
      <div className="relative hidden lg:flex flex-col justify-between p-12 bg-slate-900 text-white overflow-hidden">
        <div
          className="absolute inset-0 opacity-30"
          style={{
            backgroundImage: "url(https://images.unsplash.com/photo-1765021690100-db6d6a28c1d1?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjY2NjV8MHwxfHNlYXJjaHwxfHxpbmR1c3RyaWFsJTIwbGF1bmRyeSUyMG1hY2hpbmUlMjBmYWNpbGl0eXxlbnwwfHx8fDE3NzY5NTUxMDR8MA&ixlib=rb-4.1.0&q=85)",
            backgroundSize: "cover",
            backgroundPosition: "center",
          }}
        />
        <div className="absolute inset-0 bg-gradient-to-br from-indaco/60 via-slate-900/80 to-slate-900/95" />
        <div className="relative z-10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-white/10 backdrop-blur-sm border border-white/20 flex items-center justify-center">
              <Sparkle size={22} weight="fill" className="text-celeste" />
            </div>
            <div>
              <div className="font-display font-bold text-2xl tracking-tight">CleanTec</div>
              <div className="text-[11px] text-celeste font-mono uppercase tracking-widest">Industrial Laundry OS</div>
            </div>
          </div>
        </div>

        <div className="relative z-10 max-w-lg">
          <div className="overline text-celeste mb-4">Control Room</div>
          <h1 className="font-display text-4xl xl:text-5xl font-bold leading-tight tracking-tight mb-6">
            Il sistema nervoso della tua lavanderia industriale.
          </h1>
          <p className="text-slate-300 text-lg leading-relaxed">
            ERP, MES, WMS e logistica in un unico ambiente. Tracciabilità capo per capo, dalla ricezione alla consegna.
          </p>

          <div className="grid grid-cols-2 gap-4 mt-10">
            {[
              { icon: Factory, label: "MES Produzione" },
              { icon: Truck, label: "TMS Logistica" },
              { icon: ShieldCheck, label: "Controllo Qualità" },
              { icon: ChartBar, label: "KPI Real-time" },
            ].map((f, i) => (
              <div key={i} className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-lg p-4 flex items-center gap-3">
                <f.icon size={22} weight="duotone" className="text-celeste" />
                <span className="text-sm font-medium">{f.label}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="relative z-10 text-xs text-slate-400 font-mono">
          © 2026 CleanTec Systems — v1.0
        </div>
      </div>

      {/* Right form */}
      <div className="flex items-center justify-center p-8 lg:p-12">
        <div className="w-full max-w-md">
          <div className="mb-10">
            <div className="overline mb-2">Accesso operatore</div>
            <h2 className="font-display text-3xl font-bold text-slate-900 tracking-tight">Bentornato in CleanTec</h2>
            <p className="text-slate-500 mt-2">Effettua l'accesso per gestire la produzione, i lotti e le consegne.</p>
          </div>

          <form onSubmit={submit} className="space-y-5" data-testid="login-form">
            <div>
              <label className="text-sm font-medium text-slate-700 block mb-1.5">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                data-testid="login-email-input"
                className="w-full px-4 py-3 bg-white border border-slate-200 rounded-md text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indaco focus:border-transparent transition-all font-mono text-sm"
                placeholder="admin@cleantec.it"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700 block mb-1.5">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                data-testid="login-password-input"
                className="w-full px-4 py-3 bg-white border border-slate-200 rounded-md text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indaco focus:border-transparent transition-all font-mono text-sm"
                placeholder="••••••••"
              />
            </div>

            {error && <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2" data-testid="login-error">{error}</div>}

            <button
              type="submit"
              disabled={loading}
              data-testid="login-submit-button"
              className="w-full bg-indaco hover:bg-indaco-dark text-white font-medium py-3 rounded-md transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-60"
            >
              <SignIn size={18} weight="bold" />
              {loading ? "Accesso in corso…" : "Accedi"}
            </button>
          </form>

          <div className="mt-10 pt-6 border-t border-slate-200">
            <div className="overline text-slate-400 mb-3">Account demo</div>
            <div className="grid grid-cols-1 gap-2">
              {[
                { e: "admin@cleantec.it", p: "admin123", r: "Admin" },
                { e: "produzione@cleantec.it", p: "produzione123", r: "Produzione" },
                { e: "logistica@cleantec.it", p: "logistica123", r: "Logistica" },
                { e: "qualita@cleantec.it", p: "qualita123", r: "Qualità" },
                { e: "contabilita@cleantec.it", p: "contabilita123", r: "Contabilità" },
              ].map((d) => (
                <button
                  key={d.e}
                  type="button"
                  onClick={() => quickLogin(d.e, d.p)}
                  data-testid={`demo-${d.r.toLowerCase()}`}
                  className="flex items-center justify-between text-xs font-mono text-slate-500 hover:text-indaco bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-md px-3 py-2 transition-colors"
                >
                  <span>{d.e}</span>
                  <span className="text-[10px] uppercase tracking-wider text-slate-400">{d.r}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
