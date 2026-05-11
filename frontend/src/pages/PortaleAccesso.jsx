import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Storefront, MagnifyingGlass, ArrowRight, ShieldCheck, Warning } from "@phosphor-icons/react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function PortaleAccesso() {
  const [ident, setIdent] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [match, setMatch] = useState(null);
  const navigate = useNavigate();

  const submit = async (e) => {
    e.preventDefault();
    if (!ident.trim()) { setErr("Inserisci P.IVA o Codice Fiscale"); return; }
    setLoading(true); setErr(""); setMatch(null);
    try {
      const { data } = await axios.post(`${API}/public/portale/lookup`, { identificativo: ident.trim() });
      setMatch(data);
    } catch (e2) {
      setErr(e2.response?.data?.detail || "Errore di connessione");
    } finally { setLoading(false); }
  };

  const proceed = () => {
    if (match?.token) navigate(`/ordina/${match.token}`);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-celeste/5 to-indaco/5 flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        {/* Brand header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-indaco to-celeste shadow-lg mb-4">
            <Storefront size={28} weight="duotone" className="text-white" />
          </div>
          <h1 className="text-3xl font-display font-bold text-slate-900">Portale ordini</h1>
          <p className="text-sm text-slate-500 mt-1">Accedi al tuo catalogo personalizzato per inviare un nuovo ordinativo.</p>
        </div>

        {/* Card */}
        <div className="bg-white rounded-2xl shadow-xl border border-slate-100 overflow-hidden">
          {!match ? (
            <form onSubmit={submit} className="p-6 space-y-4">
              <div>
                <label className="block text-xs uppercase tracking-wide font-mono text-slate-600 mb-2">
                  Identificati con
                </label>
                <div className="relative">
                  <MagnifyingGlass size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    autoFocus
                    value={ident}
                    onChange={e => setIdent(e.target.value.toUpperCase())}
                    placeholder="P.IVA  oppure  Codice Fiscale"
                    className="w-full pl-10 pr-4 py-3 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indaco focus:border-indaco text-sm font-mono"
                    data-testid="portale-input-ident"
                  />
                </div>
                <p className="text-[11px] text-slate-400 mt-1">Es. IT01234567890 oppure RSSMRA80A01H501Z</p>
              </div>

              {err && (
                <div className="flex items-start gap-2 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
                  <Warning size={16} weight="fill" className="flex-shrink-0 mt-0.5" />
                  <span>{err}</span>
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full bg-indaco hover:bg-indaco-dark text-white py-3 rounded-lg font-medium flex items-center justify-center gap-2 transition disabled:opacity-50"
                data-testid="portale-submit">
                {loading ? "Verifica in corso…" : "Accedi al catalogo"}
                {!loading && <ArrowRight size={16} weight="bold" />}
              </button>

              <div className="flex items-center gap-2 text-[11px] text-slate-400 pt-2 border-t border-slate-100">
                <ShieldCheck size={14} weight="fill" className="text-emerald-500" />
                <span>Accesso sicuro · Sessione di 1 ora</span>
              </div>
            </form>
          ) : (
            <div className="p-6 space-y-4" data-testid="portale-confirm">
              <div className="flex flex-col items-center text-center">
                <div className="w-14 h-14 rounded-full bg-emerald-100 flex items-center justify-center mb-3">
                  <ShieldCheck size={28} weight="fill" className="text-emerald-600" />
                </div>
                <p className="text-xs uppercase tracking-wide font-mono text-slate-500">Cliente identificato</p>
                <h2 className="text-xl font-display font-bold text-slate-900 mt-1">{match.cliente.ragione_sociale}</h2>
                {match.cliente.denominazione_struttura && match.cliente.denominazione_struttura !== match.cliente.ragione_sociale && (
                  <p className="text-sm text-slate-600">{match.cliente.denominazione_struttura}</p>
                )}
                {match.cliente.indirizzo && (
                  <p className="text-xs text-slate-400 mt-1">{match.cliente.indirizzo}</p>
                )}
              </div>

              <div className="flex gap-2">
                <button
                  onClick={() => { setMatch(null); setIdent(""); }}
                  className="flex-1 border border-slate-200 hover:bg-slate-50 text-slate-700 py-3 rounded-lg text-sm transition"
                  data-testid="portale-back">
                  Non sono io
                </button>
                <button
                  onClick={proceed}
                  className="flex-1 bg-indaco hover:bg-indaco-dark text-white py-3 rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition"
                  data-testid="portale-proceed">
                  Continua <ArrowRight size={16} weight="bold" />
                </button>
              </div>
            </div>
          )}
        </div>

        <p className="text-center text-[11px] text-slate-400 mt-6">
          Non riesci ad accedere? Contatta direttamente il tuo referente commerciale.
        </p>
      </div>
    </div>
  );
}
