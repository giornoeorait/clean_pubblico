import React, { useEffect, useState } from "react";
import api from "../lib/api";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Switch } from "../components/ui/switch";
import { Label } from "../components/ui/label";
import { Printer, Copy, CheckCircle, Monitor, Warning, DeviceTablet } from "@phosphor-icons/react";

const KIOSK_CMD = '"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --kiosk-printing --kiosk https://cleantec.app/produzione';

export default function ImpostazioniStampa() {
  const [cfg, setCfg] = useState(null);
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState(false);
  const [printer, setPrinter] = useState(null);
  const [testMsg, setTestMsg] = useState(null);

  const loadPrinter = () => api.get("/stampante-ddt").then(r => setPrinter(r.data)).catch(() => {});

  useEffect(() => {
    api.get("/stampa-settings").then(r => setCfg(r.data)).catch(() => setCfg({ auto_print_ddt: true, nome_stampante: "" }));
    loadPrinter();
  }, []);

  const savePrinter = async () => {
    setSaving(true);
    try {
      const { ip, porta, protocollo, formato, colore, copie, fronte_retro, vassoio } = printer;
      await api.put("/stampante-ddt", { ip, porta: Number(porta), protocollo, formato, colore, copie: Number(copie), fronte_retro, vassoio });
      toast.success("Stampante DDT salvata");
      loadPrinter();
    } catch (e) { toast.error(e.response?.data?.detail || "Errore salvataggio"); }
    setSaving(false);
  };

  const runJob = async (tipo) => {
    setTestMsg({ text: tipo === "check" ? "Verifica connessione in corso…" : "Invio pagina di prova…", ok: null });
    try {
      const { data: job } = await api.post("/print-jobs", { tipo });
      for (let i = 0; i < 15; i++) {
        await new Promise(r => setTimeout(r, 1500));
        const { data: j } = await api.get(`/print-jobs/${job.id}`);
        if (j.stato === "printed") { setTestMsg({ text: tipo === "check" ? "✓ Stampante raggiungibile" : "✓ Pagina di prova inviata alla stampante", ok: true }); return; }
        if (j.stato === "failed") { setTestMsg({ text: `✗ ${j.errore || "Stampante non raggiungibile"}`, ok: false }); return; }
      }
      setTestMsg({ text: "✗ Nessuna risposta dal Print Bridge (è avviato sul PC in lavanderia?)", ok: false });
    } catch (e) { setTestMsg({ text: `✗ ${e.response?.data?.detail || "Errore"}`, ok: false }); }
  };

  const rigeneraToken = async () => {
    const { data } = await api.post("/stampante-ddt/bridge-token");
    setPrinter(p => ({ ...p, bridge_token: data.bridge_token }));
    toast.success("Token rigenerato — aggiorna il bridge sul PC");
  };

  const scaricaBridge = async () => {
    const res = await api.get("/print-bridge/script", { responseType: "blob" });
    const url = URL.createObjectURL(new Blob([res.data]));
    const a = document.createElement("a");
    a.href = url; a.download = "cleantec_print_bridge.py"; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  };

  const save = async (next) => {
    setSaving(true);
    try {
      const { data } = await api.put("/stampa-settings", next);
      setCfg(data);
      toast.success("Impostazioni stampa salvate");
    } catch { toast.error("Errore salvataggio"); }
    setSaving(false);
  };

  const copyCmd = async () => {
    try {
      await navigator.clipboard.writeText(KIOSK_CMD);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch { toast.error("Copia manuale: seleziona il testo"); }
  };

  if (!cfg) return <div className="text-sm text-slate-400 p-6">Caricamento…</div>;

  return (
    <div className="space-y-6 max-w-3xl" data-testid="stampa-settings-page">
      <div>
        <h1 className="font-display text-2xl md:text-3xl font-bold flex items-center gap-2"><Printer size={28} className="text-indaco" />Stampa & Totem</h1>
        <p className="text-sm text-slate-500">Configurazione stampa automatica dei DDT dal totem produzione</p>
      </div>

      <div className="kpi-card p-5 space-y-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <Label className="text-base font-semibold">Stampa automatica DDT dal totem</Label>
            <p className="text-xs text-slate-500 mt-1">Alla chiusura di un ordine ("Finisci e trasforma in DDT") il PDF del DDT viene inviato in stampa automaticamente.</p>
          </div>
          <Switch checked={cfg.auto_print_ddt} disabled={saving}
            onCheckedChange={(v) => save({ ...cfg, auto_print_ddt: v })}
            data-testid="auto-print-switch" />
        </div>
        <div>
          <Label>Stampante di default (promemoria)</Label>
          <Input value={cfg.nome_stampante} placeholder="Es. HP LaserJet Ufficio (impostata come predefinita in Windows)"
            onChange={e => setCfg({ ...cfg, nome_stampante: e.target.value })}
            onBlur={() => save(cfg)} data-testid="nome-stampante-input" className="mt-1" />
          <p className="text-xs text-slate-500 mt-1">Nota: per motivi di sicurezza il browser stampa sempre sulla <b>stampante predefinita di Windows</b>. Questo campo è un promemoria di quale stampante deve essere impostata come predefinita sul PC del totem.</p>
        </div>
      </div>

      <div className="kpi-card p-5 space-y-4" data-testid="stampante-ddt-card">
        <div className="flex items-center justify-between">
          <h3 className="font-display font-bold text-base flex items-center gap-2"><Printer size={20} className="text-indaco" />Stampante DDT — stampa diretta in rete (Print Bridge)</h3>
          {printer && (
            <span className={`text-xs font-bold px-3 py-1 rounded-full ${printer.bridge_online ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-600"}`} data-testid="bridge-status">
              Bridge {printer.bridge_online ? "ONLINE" : "OFFLINE"}
            </span>
          )}
        </div>
        <p className="text-sm text-slate-600">Stampa <b>realmente silenziosa</b> anche da tablet Android: il server accoda i DDT e un piccolo programma ("Print Bridge") su un PC della lavanderia li invia alla stampante di rete (es. Ricoh MP C4503) via IPP o RAW 9100.</p>
        {printer && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="col-span-2"><Label>IP stampante</Label><Input value={printer.ip || ""} onChange={e => setPrinter({ ...printer, ip: e.target.value })} placeholder="es. 192.168.1.50" data-testid="printer-ip" /></div>
              <div><Label>Porta</Label><Input type="number" value={printer.porta} onChange={e => setPrinter({ ...printer, porta: e.target.value })} data-testid="printer-porta" /></div>
              <div><Label>Protocollo</Label>
                <select value={printer.protocollo} onChange={e => setPrinter({ ...printer, protocollo: e.target.value, porta: e.target.value === "ipp" ? 631 : 9100 })}
                  className="w-full h-9 rounded-md border border-input bg-background px-2 text-sm" data-testid="printer-protocollo">
                  <option value="ipp">IPP (porta 631, consigliato)</option>
                  <option value="raw">RAW TCP (porta 9100)</option>
                </select>
              </div>
              <div><Label>Formato</Label><Input value={printer.formato} onChange={e => setPrinter({ ...printer, formato: e.target.value })} /></div>
              <div><Label>Copie</Label><Input type="number" min="1" max="10" value={printer.copie} onChange={e => setPrinter({ ...printer, copie: e.target.value })} /></div>
              <div className="flex items-end gap-2 pb-1"><Switch checked={!!printer.colore} onCheckedChange={v => setPrinter({ ...printer, colore: v })} /><span className="text-sm">Colore</span></div>
              <div className="flex items-end gap-2 pb-1"><Switch checked={!!printer.fronte_retro} onCheckedChange={v => setPrinter({ ...printer, fronte_retro: v })} /><span className="text-sm">Fronte/retro</span></div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={savePrinter} disabled={saving} className="bg-indaco hover:bg-indaco/90" data-testid="save-printer-btn">Salva stampante</Button>
              <Button size="sm" variant="outline" onClick={() => runJob("check")} disabled={!printer.configurata} data-testid="verifica-connessione-btn">Verifica connessione</Button>
              <Button size="sm" variant="outline" onClick={() => runJob("test")} disabled={!printer.configurata} data-testid="stampa-prova-btn">Stampa pagina di prova</Button>
            </div>
            {testMsg && <div className={`text-sm rounded-lg p-3 ${testMsg.ok === true ? "bg-emerald-50 text-emerald-700" : testMsg.ok === false ? "bg-red-50 text-red-600" : "bg-slate-50 text-slate-600"}`} data-testid="test-msg">{testMsg.text}</div>}

            <div className="border-t border-slate-200 pt-4 space-y-3">
              <h4 className="font-bold text-sm">Installazione Print Bridge (una tantum, su un PC della lavanderia)</h4>
              <ol className="text-sm text-slate-700 space-y-2 list-decimal list-inside">
                <li>Serve un PC (anche mini-PC/Raspberry) <b>sulla stessa rete della stampante</b>, con Python 3 installato</li>
                <li><button onClick={scaricaBridge} className="text-indaco underline font-semibold" data-testid="scarica-bridge-btn">Scarica cleantec_print_bridge.py</button> e copialo sul PC</li>
                <li>Avvialo con: <code className="bg-slate-900 text-emerald-300 text-xs px-2 py-1 rounded">python3 cleantec_print_bridge.py --server https://cleantec.app --token &lt;token qui sotto&gt;</code></li>
                <li>Quando il badge in alto diventa <b>ONLINE</b>, usa "Verifica connessione" e poi "Stampa pagina di prova"</li>
              </ol>
              <div className="flex items-center gap-2">
                <code className="flex-1 bg-slate-900 text-emerald-300 text-xs p-3 rounded-lg overflow-x-auto whitespace-nowrap" data-testid="bridge-token">{printer.bridge_token || "Nessun token — generane uno"}</code>
                <Button variant="outline" size="sm" onClick={() => { navigator.clipboard.writeText(printer.bridge_token || ""); toast.success("Token copiato"); }} disabled={!printer.bridge_token}><Copy size={16} /></Button>
                <Button variant="outline" size="sm" onClick={rigeneraToken} data-testid="rigenera-token-btn">{printer.bridge_token ? "Rigenera" : "Genera token"}</Button>
              </div>
              <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-800">
                <Warning size={18} className="flex-shrink-0 mt-0.5" />
                <span><b>Nota sulla Ricoh MP C4503:</b> il bridge prova prima IPP (che conferma l'accettazione del job) e in automatico ripiega su RAW 9100. La stampa RAW di PDF richiede l'opzione <b>PostScript3/PDF Direct</b> sulla stampante: se la pagina di prova non esce, verifica dal pannello Ricoh che il supporto PDF Direct sia attivo. Se il bridge è offline o la stampa fallisce, il totem propone automaticamente <b>PrintHand</b> (con conferma) o il download del PDF — il DDT resta comunque salvato, senza numeri duplicati.</span>
              </div>
            </div>
          </>
        )}
      </div>

      <div className="kpi-card p-5 space-y-4">
        <h3 className="font-display font-bold text-base flex items-center gap-2"><Monitor size={20} className="text-indaco" />Stampa silenziosa — configurazione Chrome Kiosk (PC Windows)</h3>
        <p className="text-sm text-slate-600">I browser mostrano sempre la finestra di stampa, TRANNE se Chrome viene avviato in modalità kiosk. Configurazione una tantum sul PC del totem:</p>
        <ol className="space-y-3 text-sm text-slate-700 list-none">
          <li className="flex gap-3"><span className="w-6 h-6 rounded-full bg-indaco text-white text-xs font-bold flex items-center justify-center flex-shrink-0">1</span>
            <span><b>Imposta la stampante predefinita</b> in Windows: Impostazioni → Bluetooth e dispositivi → Stampanti → scegli la stampante → "Imposta come predefinita" (disattiva "Consenti a Windows di gestire la stampante predefinita").</span></li>
          <li className="flex gap-3"><span className="w-6 h-6 rounded-full bg-indaco text-white text-xs font-bold flex items-center justify-center flex-shrink-0">2</span>
            <span><b>Crea un collegamento sul desktop</b>: tasto destro sul desktop → Nuovo → Collegamento, e incolla come destinazione:</span></li>
        </ol>
        <div className="flex items-center gap-2">
          <code className="flex-1 bg-slate-900 text-emerald-300 text-xs p-3 rounded-lg overflow-x-auto whitespace-nowrap" data-testid="kiosk-cmd">{KIOSK_CMD}</code>
          <Button variant="outline" size="sm" onClick={copyCmd} data-testid="copy-cmd-btn">
            {copied ? <CheckCircle size={16} className="text-emerald-600" /> : <Copy size={16} />}
          </Button>
        </div>
        <ol className="space-y-3 text-sm text-slate-700 list-none">
          <li className="flex gap-3"><span className="w-6 h-6 rounded-full bg-indaco text-white text-xs font-bold flex items-center justify-center flex-shrink-0">3</span>
            <span><b>Chiamalo "Totem CleanTec"</b> e usa SEMPRE questo collegamento per avviare il totem. Chrome si aprirà a tutto schermo direttamente sulla pagina di produzione e <b>ogni stampa partirà immediatamente</b> sulla stampante predefinita, senza finestre.</span></li>
          <li className="flex gap-3"><span className="w-6 h-6 rounded-full bg-indaco text-white text-xs font-bold flex items-center justify-center flex-shrink-0">4</span>
            <span>Per uscire dalla modalità kiosk: <b>ALT + F4</b>. Suggerimento: metti il collegamento in Esecuzione automatica per l'avvio col PC.</span></li>
        </ol>
        <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
          <DeviceTablet size={20} className="flex-shrink-0 mt-0.5" />
          <span><b>Tablet Android/iPad:</b> la modalità kiosk-printing non è disponibile — apparirà la finestra di stampa di sistema. Per la stampa silenziosa usa un PC Windows (anche mini-PC) collegato al touch screen.</span>
        </div>
        <div className="flex items-start gap-2 bg-slate-50 border border-slate-200 rounded-lg p-3 text-sm text-slate-600">
          <Warning size={20} className="flex-shrink-0 mt-0.5" />
          <span>Chrome deve restare aperto dal collegamento kiosk: se il totem viene aperto da un Chrome normale, la finestra di stampa tornerà a comparire.</span>
        </div>
      </div>
    </div>
  );
}
