import React, { useCallback, useEffect, useRef, useState } from "react";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import {
  ArrowLeft, CheckCircle, Circle, Play, Printer, SignOut, Timer,
  Basket, User, Warning, CheckFat, SignIn,
} from "@phosphor-icons/react";

const POLL_MS = 20000;

function playBeep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.connect(g); g.connect(ctx.destination);
    o.type = "sine"; o.frequency.value = 880;
    g.gain.setValueAtTime(0.4, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.6);
    o.start(); o.stop(ctx.currentTime + 0.6);
    setTimeout(() => { const o2 = ctx.createOscillator(); const g2 = ctx.createGain(); o2.connect(g2); g2.connect(ctx.destination); o2.type = "sine"; o2.frequency.value = 1174; g2.gain.setValueAtTime(0.4, ctx.currentTime); g2.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.6); o2.start(); o2.stop(ctx.currentTime + 0.6); }, 250);
  } catch {}
}

function elapsedLabel(iso) {
  if (!iso) return "";
  const min = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (min < 60) return `${min} min fa`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h}h ${min % 60}m fa`;
  return `${Math.floor(h / 24)}g fa`;
}

function fmtConsegna(d) {
  if (!d) return "—";
  try { return new Date(d).toLocaleDateString("it-IT", { weekday: "short", day: "2-digit", month: "2-digit" }); } catch { return d; }
}

const clienteName = (o) => o.cliente_snapshot?.denominazione_struttura || o.cliente_snapshot?.ragione_sociale || "Cliente";

// ---------- Login totem ----------
function TotemLogin() {
  const { login, error } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    await login(email, password);
    setLoading(false);
  };
  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-8">
      <form onSubmit={submit} className="w-full max-w-lg bg-slate-900 border border-slate-700 rounded-2xl p-10 space-y-6" data-testid="totem-login-form">
        <div className="text-center">
          <div className="text-emerald-400 font-mono uppercase tracking-[0.3em] text-sm mb-2">Totem Produzione</div>
          <h1 className="font-display text-4xl font-bold text-white">CleanTec Lavanderia</h1>
          <p className="text-slate-400 mt-2 text-lg">Accedi una sola volta — la sessione resta attiva 90 giorni</p>
        </div>
        <input type="email" value={email} onChange={e => setEmail(e.target.value)} required placeholder="Email totem"
          data-testid="totem-login-email"
          className="w-full px-6 py-5 text-2xl bg-slate-800 border border-slate-600 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500" />
        <input type="password" value={password} onChange={e => setPassword(e.target.value)} required placeholder="Password"
          data-testid="totem-login-password"
          className="w-full px-6 py-5 text-2xl bg-slate-800 border border-slate-600 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500" />
        {error && <div className="text-red-400 bg-red-950/50 border border-red-800 rounded-xl px-4 py-3 text-lg" data-testid="totem-login-error">{error}</div>}
        <button type="submit" disabled={loading} data-testid="totem-login-submit"
          className="w-full py-6 bg-emerald-600 hover:bg-emerald-500 active:scale-[0.98] text-white text-2xl font-bold rounded-xl flex items-center justify-center gap-3 transition-all disabled:opacity-50">
          <SignIn size={28} weight="bold" />{loading ? "Accesso…" : "ACCEDI"}
        </button>
      </form>
    </div>
  );
}

// ---------- Board card ----------
function OrderCard({ o, onOpen }) {
  const isNew = o.stato === "nuovo";
  const done = (o.righe_eseguite || []).filter(Boolean).length;
  const tot = (o.righe || []).length;
  return (
    <button onClick={() => onOpen(o)} data-testid={`totem-order-card-${o.numero}`}
      className={`text-left w-full rounded-2xl border-2 p-6 transition-all active:scale-[0.98] ${isNew ? "bg-amber-950/40 border-amber-500/60 hover:border-amber-400" : "bg-sky-950/40 border-sky-500/60 hover:border-sky-400"}`}>
      <div className="flex items-center justify-between mb-3">
        <span className={`px-4 py-1.5 rounded-full text-sm font-bold uppercase tracking-wider ${isNew ? "bg-amber-500 text-amber-950" : "bg-sky-500 text-sky-950"}`}>
          {isNew ? "Nuovo" : "In lavorazione"}
        </span>
        <span className="font-mono text-slate-400 text-lg">{o.numero}</span>
      </div>
      <div className="font-display text-2xl font-bold text-white leading-tight mb-2">{clienteName(o)}</div>
      <div className="flex items-center gap-5 text-slate-300 text-lg">
        <span className="flex items-center gap-2"><Basket size={22} />{(o.righe || []).reduce((s, r) => s + (r.quantita || 0), 0)} pz</span>
        <span className="flex items-center gap-2"><Timer size={22} />Consegna: <b className="text-white">{fmtConsegna(o.data_consegna_richiesta)}</b></span>
      </div>
      <div className="flex items-center justify-between mt-3">
        <span className="text-slate-500 text-base">{elapsedLabel(o.data_richiesta || o.created_at)}</span>
        {!isNew && (
          <span className="flex items-center gap-2 text-base text-sky-300">
            {o.operatore_produzione && <span className="flex items-center gap-1"><User size={18} />{o.operatore_produzione}</span>}
            <span className="font-mono font-bold">{done}/{tot} righe</span>
          </span>
        )}
      </div>
    </button>
  );
}

// ---------- Detail view ----------
function OrderDetail({ order, onBack, onFinalized }) {
  const [o, setO] = useState(order);
  const [flags, setFlags] = useState(() => {
    const f = order.righe_eseguite || [];
    return (order.righe || []).map((_, i) => !!f[i]);
  });
  const [operatorAsk, setOperatorAsk] = useState(false);
  const [operatorName, setOperatorName] = useState(order.operatore_produzione || "");
  const [confirmIncomplete, setConfirmIncomplete] = useState(false);
  const [busy, setBusy] = useState(false);

  const isNew = o.stato === "nuovo";
  const doneCount = flags.filter(Boolean).length;
  const totRows = (o.righe || []).length;
  const allDone = doneCount === totRows && totRows > 0;

  const startLavorazione = async () => {
    if (!operatorName.trim()) return;
    setBusy(true);
    try {
      const { data } = await api.patch(`/ordinativi/${o.id}/produzione`, { stato: "in_lavorazione", operatore: operatorName.trim() });
      setO(data);
      setOperatorAsk(false);
    } catch (e) { alert(e.response?.data?.detail || "Errore"); }
    setBusy(false);
  };

  const toggleRow = async (i) => {
    if (isNew) return;
    const next = flags.map((v, j) => j === i ? !v : v);
    setFlags(next);
    try { await api.patch(`/ordinativi/${o.id}/produzione`, { righe_eseguite: next }); }
    catch { setFlags(flags); }
  };

  const finalize = async () => {
    setConfirmIncomplete(false);
    setBusy(true);
    try {
      const { data } = await api.post(`/ordinativi/${o.id}/converti-ddt`);
      onFinalized(data);
    } catch (e) { alert(e.response?.data?.detail || "Errore conversione DDT"); setBusy(false); }
  };

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 bg-slate-900 border-b border-slate-700 sticky top-0 z-20">
        <button onClick={onBack} data-testid="totem-back-btn"
          className="flex items-center gap-3 px-8 py-4 bg-slate-700 hover:bg-slate-600 active:scale-95 text-white text-xl font-bold rounded-xl transition-all">
          <ArrowLeft size={26} weight="bold" />INDIETRO
        </button>
        <div className="text-center">
          <div className="font-mono text-slate-400 text-lg">{o.numero}</div>
          <div className="font-display text-2xl font-bold text-white">{clienteName(o)}</div>
        </div>
        <div className="text-right">
          <div className="text-slate-400 text-sm uppercase tracking-wider">Consegna richiesta</div>
          <div className="text-white text-xl font-bold">{fmtConsegna(o.data_consegna_richiesta)}</div>
        </div>
      </div>

      {/* Progress bar */}
      <div className="px-6 pt-5">
        <div className="flex items-center justify-between mb-2">
          <span className="text-slate-300 text-xl font-semibold" data-testid="totem-progress-label">{doneCount} / {totRows} righe completate</span>
          {o.operatore_produzione && <span className="flex items-center gap-2 text-sky-300 text-lg"><User size={22} />{o.operatore_produzione}</span>}
        </div>
        <div className="h-4 bg-slate-800 rounded-full overflow-hidden">
          <div className="h-full bg-emerald-500 transition-all duration-300" style={{ width: totRows ? `${(doneCount / totRows) * 100}%` : "0%" }} />
        </div>
      </div>

      {/* Rows */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4 pb-40">
        {isNew && (
          <div className="bg-amber-950/50 border-2 border-amber-500/60 rounded-2xl p-5 text-amber-200 text-xl flex items-center gap-3">
            <Warning size={30} weight="fill" className="text-amber-400 flex-shrink-0" />
            Premi "METTI IN LAVORAZIONE" per iniziare a spuntare le righe.
          </div>
        )}
        {(o.righe || []).map((r, i) => (
          <button key={i} onClick={() => toggleRow(i)} disabled={isNew} data-testid={`totem-row-${i}`}
            className={`w-full flex items-center gap-5 p-5 rounded-2xl border-2 text-left transition-all active:scale-[0.99] ${flags[i] ? "bg-emerald-950/50 border-emerald-500/70" : "bg-slate-900 border-slate-700"} ${isNew ? "opacity-50" : ""}`}>
            {flags[i]
              ? <CheckCircle size={44} weight="fill" className="text-emerald-400 flex-shrink-0" />
              : <Circle size={44} className="text-slate-500 flex-shrink-0" />}
            <div className="flex-1 min-w-0">
              <div className={`text-2xl font-bold ${flags[i] ? "text-emerald-200 line-through" : "text-white"}`}>{r.descrizione}</div>
              <div className="text-slate-400 text-lg font-mono">{r.codice}</div>
            </div>
            <div className={`text-3xl font-bold font-mono ${flags[i] ? "text-emerald-300" : "text-white"}`}>
              {r.quantita} <span className="text-lg text-slate-400">{r.unita_misura || "pz"}</span>
            </div>
          </button>
        ))}
        {(o.note_cliente || o.note_interne) && (
          <div className="bg-slate-900 border border-slate-700 rounded-2xl p-5 text-slate-300 text-lg">
            {o.note_cliente && <div><b className="text-white">Note cliente:</b> {o.note_cliente}</div>}
            {o.note_interne && <div><b className="text-white">Note interne:</b> {o.note_interne}</div>}
          </div>
        )}
      </div>

      {/* Bottom actions */}
      <div className="fixed bottom-0 left-0 right-0 p-5 bg-slate-900/95 backdrop-blur border-t border-slate-700 flex gap-4">
        {isNew ? (
          <button onClick={() => setOperatorAsk(true)} disabled={busy} data-testid="totem-start-btn"
            className="flex-1 py-6 bg-sky-600 hover:bg-sky-500 active:scale-[0.98] text-white text-2xl font-bold rounded-xl flex items-center justify-center gap-3 transition-all disabled:opacity-50">
            <Play size={30} weight="fill" />METTI IN LAVORAZIONE
          </button>
        ) : (
          <button onClick={() => allDone ? finalize() : setConfirmIncomplete(true)} disabled={busy} data-testid="totem-finish-btn"
            className={`flex-1 py-6 text-2xl font-bold rounded-xl flex items-center justify-center gap-3 transition-all active:scale-[0.98] disabled:opacity-50 ${allDone ? "bg-emerald-600 hover:bg-emerald-500 text-white" : "bg-slate-700 hover:bg-slate-600 text-slate-300"}`}>
            <Printer size={30} weight="bold" />{busy ? "CONVERSIONE…" : "FINISCI E TRASFORMA IN DDT"}
          </button>
        )}
      </div>

      {/* Operator name overlay */}
      {operatorAsk && (
        <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-6">
          <div className="w-full max-w-xl bg-slate-900 border-2 border-sky-500/60 rounded-2xl p-8 space-y-6" data-testid="totem-operator-modal">
            <h3 className="font-display text-3xl font-bold text-white text-center">Chi lavora questo ordine?</h3>
            <input autoFocus value={operatorName} onChange={e => setOperatorName(e.target.value)} placeholder="Nome operatore"
              data-testid="totem-operator-input"
              className="w-full px-6 py-5 text-3xl text-center bg-slate-800 border border-slate-600 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-sky-500" />
            <div className="flex gap-4">
              <button onClick={() => setOperatorAsk(false)} className="flex-1 py-5 bg-slate-700 text-white text-xl font-bold rounded-xl active:scale-95">Annulla</button>
              <button onClick={startLavorazione} disabled={!operatorName.trim() || busy} data-testid="totem-operator-confirm"
                className="flex-1 py-5 bg-sky-600 hover:bg-sky-500 text-white text-xl font-bold rounded-xl active:scale-95 disabled:opacity-40">CONFERMA</button>
            </div>
          </div>
        </div>
      )}

      {/* Confirm incomplete overlay */}
      {confirmIncomplete && (
        <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-6">
          <div className="w-full max-w-xl bg-slate-900 border-2 border-amber-500/60 rounded-2xl p-8 space-y-6 text-center" data-testid="totem-confirm-incomplete">
            <Warning size={60} weight="fill" className="text-amber-400 mx-auto" />
            <h3 className="font-display text-3xl font-bold text-white">Mancano {totRows - doneCount} righe da spuntare</h3>
            <p className="text-slate-300 text-xl">Vuoi comunque finalizzare l'ordine e creare il DDT?</p>
            <div className="flex gap-4">
              <button onClick={() => setConfirmIncomplete(false)} className="flex-1 py-5 bg-slate-700 text-white text-xl font-bold rounded-xl active:scale-95">NO, TORNA</button>
              <button onClick={finalize} data-testid="totem-confirm-incomplete-yes"
                className="flex-1 py-5 bg-amber-600 hover:bg-amber-500 text-white text-xl font-bold rounded-xl active:scale-95">SÌ, FINALIZZA</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------- Main page ----------
export default function Produzione() {
  const { user, logout } = useAuth();
  const [orders, setOrders] = useState(null);
  const [selected, setSelected] = useState(null);
  const [newAlert, setNewAlert] = useState(false);
  const [successBadge, setSuccessBadge] = useState(null); // {numero, ddt_numero}
  const knownIds = useRef(null);

  const fetchOrders = useCallback(async () => {
    try {
      const [nuovi, lav] = await Promise.all([
        api.get("/ordinativi?stato=nuovo"),
        api.get("/ordinativi?stato=in_lavorazione"),
      ]);
      const all = [...nuovi.data, ...lav.data].sort((a, b) => {
        const da = a.data_consegna_richiesta || "9999", db_ = b.data_consegna_richiesta || "9999";
        return da === db_ ? (a.data_richiesta || "").localeCompare(b.data_richiesta || "") : da.localeCompare(db_);
      });
      if (knownIds.current !== null) {
        const fresh = all.filter(o => o.stato === "nuovo" && !knownIds.current.has(o.id));
        if (fresh.length > 0) { playBeep(); setNewAlert(true); setTimeout(() => setNewAlert(false), 8000); }
      }
      knownIds.current = new Set(all.map(o => o.id));
      setOrders(all);
    } catch {}
  }, []);

  useEffect(() => {
    if (!user || user === false) return;
    fetchOrders();
    const t = setInterval(fetchOrders, POLL_MS);
    return () => clearInterval(t);
  }, [user, fetchOrders]);

  const printDdt = async (ddtId) => {
    try {
      const res = await api.get(`/ddt/${ddtId}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const iframe = document.createElement("iframe");
      iframe.style.display = "none";
      iframe.src = url;
      document.body.appendChild(iframe);
      iframe.onload = () => {
        try { iframe.contentWindow.print(); } catch {}
        setTimeout(() => { URL.revokeObjectURL(url); iframe.remove(); }, 60000);
      };
      return true;
    } catch { return false; }
  };

  const onFinalized = async (converted) => {
    const printed = converted.ddt_id ? await printDdt(converted.ddt_id) : false;
    setSelected(null);
    setSuccessBadge({ numero: converted.numero, ddt_numero: converted.ddt_numero, printed });
    setTimeout(() => setSuccessBadge(null), 12000);
    fetchOrders();
  };

  if (user === null) return <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400 text-2xl">Verifica sessione…</div>;
  if (user === false) return <TotemLogin />;

  if (selected) {
    return <OrderDetail order={selected} onBack={() => { setSelected(null); fetchOrders(); }} onFinalized={onFinalized} />;
  }

  const nuovi = (orders || []).filter(o => o.stato === "nuovo");
  const inLav = (orders || []).filter(o => o.stato === "in_lavorazione");

  return (
    <div className="min-h-screen bg-slate-950" data-testid="totem-board">
      {/* Header */}
      <div className={`px-6 py-4 border-b flex items-center justify-between sticky top-0 z-20 transition-colors ${newAlert ? "bg-amber-600 border-amber-500 animate-pulse" : "bg-slate-900 border-slate-700"}`}>
        <div>
          <div className="text-emerald-400 font-mono uppercase tracking-[0.25em] text-xs">Totem Produzione</div>
          <h1 className="font-display text-3xl font-bold text-white">{newAlert ? "⚠ NUOVO ORDINE ARRIVATO!" : "Ordini in Lavanderia"}</h1>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right hidden sm:block">
            <div className="text-white font-mono text-2xl">{new Date().toLocaleDateString("it-IT", { weekday: "long", day: "2-digit", month: "long" })}</div>
          </div>
          <button onClick={logout} data-testid="totem-logout-btn" title="Esci"
            className="p-4 bg-slate-800 hover:bg-slate-700 text-slate-400 rounded-xl active:scale-95 transition-all">
            <SignOut size={26} />
          </button>
        </div>
      </div>

      {/* Success badge */}
      {successBadge && (
        <div className="mx-6 mt-5 bg-emerald-950/70 border-2 border-emerald-500 rounded-2xl p-5 flex items-center gap-4" data-testid="totem-success-badge">
          <CheckFat size={44} weight="fill" className="text-emerald-400 flex-shrink-0" />
          <div>
            <div className="text-emerald-200 text-2xl font-bold">Ordine {successBadge.numero} chiuso → DDT {successBadge.ddt_numero} creato</div>
            <div className="text-emerald-400 text-lg">{successBadge.printed ? "🖨 Stampa DDT avviata" : "⚠ Stampa non avviata — apri il DDT dal gestionale"}</div>
          </div>
        </div>
      )}

      <div className="p-6 grid lg:grid-cols-2 gap-8">
        {/* Nuovi */}
        <div>
          <h2 className="flex items-center gap-3 text-amber-400 font-display text-2xl font-bold mb-4">
            <span className="w-4 h-4 rounded-full bg-amber-400 animate-pulse" />In arrivo ({nuovi.length})
          </h2>
          <div className="space-y-4">
            {nuovi.map(o => <OrderCard key={o.id} o={o} onOpen={setSelected} />)}
            {orders && nuovi.length === 0 && <div className="text-slate-600 text-xl p-6 border-2 border-dashed border-slate-800 rounded-2xl text-center">Nessun nuovo ordine</div>}
          </div>
        </div>
        {/* In lavorazione */}
        <div>
          <h2 className="flex items-center gap-3 text-sky-400 font-display text-2xl font-bold mb-4">
            <span className="w-4 h-4 rounded-full bg-sky-400" />In lavorazione ({inLav.length})
          </h2>
          <div className="space-y-4">
            {inLav.map(o => <OrderCard key={o.id} o={o} onOpen={setSelected} />)}
            {orders && inLav.length === 0 && <div className="text-slate-600 text-xl p-6 border-2 border-dashed border-slate-800 rounded-2xl text-center">Nessun ordine in lavorazione</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
