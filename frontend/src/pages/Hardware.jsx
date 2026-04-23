import React, { useCallback, useEffect, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Scan, Barcode, Scales, WifiHigh, CheckCircle, XCircle, ArrowsClockwise } from "@phosphor-icons/react";
import { toast } from "sonner";

const EVENT_ICON = { barcode: Barcode, scale: Scales, rfid: WifiHigh, rfid_batch: WifiHigh };
const EVENT_COLOR = {
  barcode: "bg-sky-100 text-sky-700",
  scale: "bg-indaco/10 text-indaco",
  rfid: "bg-purple-100 text-purple-700",
  rfid_batch: "bg-purple-100 text-purple-700",
};

export default function Hardware() {
  const [events, setEvents] = useState([]);
  const [kindFilter, setKindFilter] = useState("");

  // Scan form
  const [scanCode, setScanCode] = useState("");
  const [lastScan, setLastScan] = useState(null);

  // Scale form
  const [lotti, setLotti] = useState([]);
  const [sLotto, setSLotto] = useState("");
  const [sKg, setSKg] = useState("");

  // RFID batch
  const [rfidTags, setRfidTags] = useState("");
  const [rfidLotto, setRfidLotto] = useState("");

  const fetchEvents = useCallback(async () => {
    const q = kindFilter ? `?kind=${kindFilter}` : "";
    const { data } = await api.get(`/hardware/events${q}`);
    setEvents(data);
  }, [kindFilter]);

  const fetchLotti = useCallback(async () => {
    const { data } = await api.get("/lotti?limit=100");
    setLotti(data);
  }, []);

  useEffect(() => { fetchEvents(); fetchLotti(); }, [fetchEvents, fetchLotti]);

  const doScan = async () => {
    if (!scanCode.trim()) { toast.error("Inserisci codice"); return; }
    try {
      const { data } = await api.post("/hardware/scan", { code: scanCode.trim(), station: "console" });
      setLastScan(data);
      toast.success(`Trovato: ${data.match}`);
      setScanCode(""); fetchEvents();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Nessun riscontro");
      setLastScan({ code: scanCode, match: null });
      fetchEvents();
    }
  };

  const doScale = async () => {
    const kg = parseFloat(sKg);
    if (!kg || kg <= 0) { toast.error("Peso kg non valido"); return; }
    try {
      const { data } = await api.post("/hardware/scale", {
        peso_kg: kg,
        lotto_id: sLotto || undefined,
        station: "console",
        stable: true,
      });
      toast.success(data.applied_to ? `Peso ${kg}kg applicato a ${data.applied_to.type}` : `Lettura ${kg}kg registrata`);
      setSKg(""); fetchEvents();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore bilancia");
    }
  };

  const doRfid = async () => {
    const tags = rfidTags.split(/[\n,;]+/).map(t => t.trim()).filter(Boolean);
    if (tags.length === 0) { toast.error("Inserisci almeno un tag"); return; }
    try {
      const { data } = await api.post("/hardware/rfid/batch", {
        tags,
        lotto_id: rfidLotto || undefined,
        station: "console",
      });
      toast.success(`${data.count} tag registrati`);
      setRfidTags(""); fetchEvents();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore RFID");
    }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Industrial IoT"
        title="Console Hardware"
        subtitle="Ingestione barcode, bilance e RFID. Endpoint REST per bridge on-premise, daemon USB o gateway IoT."
      />

      {/* 3 cards operative */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        {/* Barcode scan */}
        <div className="kpi-card" data-testid="hw-scan-card">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-10 h-10 rounded-lg bg-sky-100 flex items-center justify-center"><Barcode size={22} weight="duotone" className="text-sky-600" /></div>
            <div><div className="overline">Scansione</div><div className="font-display font-bold">Barcode / QR</div></div>
          </div>
          <div className="space-y-2">
            <Input autoFocus placeholder="Scansiona o digita codice…" value={scanCode} onChange={e => setScanCode(e.target.value)} onKeyDown={e => e.key === "Enter" && doScan()} data-testid="hw-scan-input" />
            <Button onClick={doScan} className="w-full bg-indaco hover:bg-indaco-dark" data-testid="hw-scan-btn"><Scan size={14} className="mr-1" />Cerca</Button>
          </div>
          {lastScan && (
            <div className={`mt-3 p-3 rounded-md text-sm border ${lastScan.match ? "bg-emerald-50 border-emerald-200" : "bg-red-50 border-red-200"}`}>
              {lastScan.match ? (
                <div>
                  <div className="font-mono font-bold text-emerald-700">✓ {lastScan.match.toUpperCase()}</div>
                  <div className="text-xs mt-1 text-slate-600">{lastScan.entity?.numero || lastScan.entity?.codice || lastScan.entity?.id}</div>
                  <div className="text-xs text-slate-500">{lastScan.entity?.descrizione || lastScan.entity?.ragione_sociale || ""}</div>
                </div>
              ) : (
                <div className="text-red-700">✗ {lastScan.code} non trovato</div>
              )}
            </div>
          )}
        </div>

        {/* Scale */}
        <div className="kpi-card" data-testid="hw-scale-card">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-10 h-10 rounded-lg bg-indaco/10 flex items-center justify-center"><Scales size={22} weight="duotone" className="text-indaco" /></div>
            <div><div className="overline">Bilancia</div><div className="font-display font-bold">Peso lotto</div></div>
          </div>
          <div className="space-y-2">
            <Select value={sLotto} onValueChange={setSLotto}>
              <SelectTrigger data-testid="hw-scale-lotto"><SelectValue placeholder="Lotto (opzionale)" /></SelectTrigger>
              <SelectContent>
                {lotti.slice(0, 50).map(l => <SelectItem key={l.id} value={l.id}>{l.numero}</SelectItem>)}
              </SelectContent>
            </Select>
            <Input type="number" step="0.1" placeholder="kg" value={sKg} onChange={e => setSKg(e.target.value)} data-testid="hw-scale-kg" />
            <Button onClick={doScale} className="w-full bg-indaco hover:bg-indaco-dark" data-testid="hw-scale-btn"><Scales size={14} className="mr-1" />Registra peso</Button>
          </div>
        </div>

        {/* RFID */}
        <div className="kpi-card" data-testid="hw-rfid-card">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-10 h-10 rounded-lg bg-purple-100 flex items-center justify-center"><WifiHigh size={22} weight="duotone" className="text-purple-600" /></div>
            <div><div className="overline">RFID Gate</div><div className="font-display font-bold">Batch tag</div></div>
          </div>
          <div className="space-y-2">
            <Select value={rfidLotto} onValueChange={setRfidLotto}>
              <SelectTrigger data-testid="hw-rfid-lotto"><SelectValue placeholder="Lotto (opzionale)" /></SelectTrigger>
              <SelectContent>
                {lotti.slice(0, 50).map(l => <SelectItem key={l.id} value={l.id}>{l.numero}</SelectItem>)}
              </SelectContent>
            </Select>
            <textarea className="w-full text-sm border border-slate-200 rounded-md p-2 font-mono" rows={3} placeholder="tag1, tag2, tag3..." value={rfidTags} onChange={e => setRfidTags(e.target.value)} data-testid="hw-rfid-tags" />
            <Button onClick={doRfid} className="w-full bg-indaco hover:bg-indaco-dark" data-testid="hw-rfid-btn"><WifiHigh size={14} className="mr-1" />Registra batch</Button>
          </div>
        </div>
      </div>

      {/* Filtri + eventi */}
      <div className="flex items-center gap-2 mb-3">
        <Label className="text-xs uppercase tracking-widest text-slate-500">Eventi</Label>
        <div className="flex gap-1">
          {["", "barcode", "scale", "rfid", "rfid_batch"].map(k => (
            <button key={k || "all"} onClick={() => setKindFilter(k)} className={`px-3 py-1 text-xs font-semibold rounded-md capitalize ${kindFilter === k ? "bg-indaco text-white" : "bg-white border border-slate-200 text-slate-600"}`} data-testid={`hw-filter-${k || "all"}`}>{k || "Tutti"}</button>
          ))}
        </div>
        <Button variant="outline" size="sm" onClick={fetchEvents} className="ml-auto"><ArrowsClockwise size={14} className="mr-1" />Refresh</Button>
      </div>

      <div className="space-y-2">
        {events.map(ev => {
          const Icon = EVENT_ICON[ev.kind] || Scan;
          return (
            <div key={ev.id} className="kpi-card flex items-center gap-3">
              <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${EVENT_COLOR[ev.kind] || "bg-slate-100"}`}>
                <Icon size={18} weight="duotone" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-xs uppercase tracking-wider font-bold text-slate-700">{ev.kind}</span>
                  <span className="text-xs text-slate-500">{ev.operatore}</span>
                </div>
                <div className="text-sm font-mono text-slate-800 mt-0.5 truncate">
                  {ev.payload?.code || ev.payload?.tag || (ev.payload?.tags ? `${ev.payload.tags.length} tag` : "") || (ev.payload?.peso_kg ? `${ev.payload.peso_kg} kg` : "")}
                </div>
              </div>
              <div className="text-xs text-slate-400 font-mono">{new Date(ev.created_at).toLocaleString("it-IT")}</div>
            </div>
          );
        })}
        {events.length === 0 && <div className="kpi-card text-center py-12 text-slate-400">Nessun evento hardware</div>}
      </div>
    </div>
  );
}
