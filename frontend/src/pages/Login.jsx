import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useBranding } from "../context/BrandingContext";
import { Sparkle, SignIn, Factory, Truck, ShieldCheck, ChartBar, Receipt, Users, Package } from "@phosphor-icons/react";
import { toast } from "sonner";

const BACKEND = process.env.REACT_APP_BACKEND_URL;
const ICON_MAP = { truck: Truck, factory: Factory, shield: ShieldCheck, chart: ChartBar, sparkle: Sparkle, receipt: Receipt, users: Users, package: Package };

export default function Login() {
  const { login, error } = useAuth();
  const { branding } = useBranding();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-white">
      {/* Left hero */}
      <div className="relative hidden lg:flex flex-col justify-between p-12 text-white overflow-hidden" style={{ backgroundColor: branding.dark_color || "#0f172a" }}>
        <div
          className="absolute inset-0 opacity-30"
          style={{
            backgroundImage: `url(${branding.hero_url ? `${BACKEND}${branding.hero_url}` : "https://images.unsplash.com/photo-1765021690100-db6d6a28c1d1?crop=entropy&cs=srgb&fm=jpg&q=70&w=1920"})`,
            backgroundSize: "cover",
            backgroundPosition: "center",
          }}
        />
        <div className="absolute inset-0" style={{ background: `linear-gradient(to bottom right, ${branding.primary_color}99, #0f172aCC, #0f172aF2)` }} />
        <div className="relative z-10">
          <div className="flex items-center gap-3">
            <div
              className="rounded-lg bg-white/10 backdrop-blur-sm border border-white/20 flex items-center justify-center overflow-hidden flex-shrink-0"
              style={{ width: "calc(40px * var(--logo-scale, 1))", height: "calc(40px * var(--logo-scale, 1))" }}
            >
              {branding.logo_url ? (
                <img src={`${BACKEND}${branding.logo_url}`} alt={branding.app_name} className="w-full h-full object-contain" />
              ) : (
                <Sparkle size={22} weight="fill" style={{ color: branding.accent_color, transform: "scale(var(--logo-scale, 1))" }} />
              )}
            </div>
            <div>
              <div className="font-display font-bold tracking-tight" style={{ fontSize: "calc(1.5rem * var(--text-scale, 1))" }}>{branding.app_name}</div>
              <div className="font-mono uppercase tracking-widest" style={{ fontSize: "calc(11px * var(--text-scale, 1))", color: branding.accent_color }}>{branding.tagline}</div>
            </div>
          </div>
        </div>

        <div className="relative z-10 max-w-lg">
          <div className="overline mb-4" style={{ color: branding.accent_color }}>{branding.login_eyebrow}</div>
          <h1 className="font-display text-4xl xl:text-5xl font-bold leading-tight tracking-tight mb-6">
            {branding.login_title}
          </h1>
          <p className="text-slate-300 text-lg leading-relaxed">
            {branding.login_subtitle}
          </p>

          <div className="grid grid-cols-2 gap-4 mt-10">
            {(branding.login_features || []).map((f, i) => {
              const Icon = ICON_MAP[f.icon] || Sparkle;
              return (
                <div key={i} className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-lg p-4 flex items-center gap-3">
                  <Icon size={22} weight="duotone" style={{ color: branding.accent_color }} />
                  <span className="text-sm font-medium">{f.label}</span>
                </div>
              );
            })}
          </div>
        </div>

        <div className="relative z-10 text-xs text-slate-400 font-mono">
          {branding.login_footer}
        </div>
      </div>

      {/* Right form */}
      <div className="flex items-center justify-center p-8 lg:p-12">
        <div className="w-full max-w-md">
          <div className="mb-10">
            <div className="overline mb-2">Accesso operatore</div>
            <h2 className="font-display text-3xl font-bold text-slate-900 tracking-tight">Bentornato in CleanTec</h2>
            <p className="text-slate-500 mt-2">Effettua l'accesso per gestire clienti, listini, D.D.T. e fatturazione.</p>
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
                placeholder="Email"
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
            <div className="text-center">
              <Link to="/pricing" className="text-sm text-indaco hover:underline font-semibold" data-testid="login-to-pricing">
                Non hai ancora un account? Inizia 14 giorni gratis →
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
