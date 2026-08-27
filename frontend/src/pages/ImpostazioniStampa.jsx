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

  useEffect(() => {
    api.get("/stampa-settings").then(r => setCfg(r.data)).catch(() => setCfg({ auto_print_ddt: true, nome_stampante: "" }));
  }, []);

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
