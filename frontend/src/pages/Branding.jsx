import React, { useCallback, useEffect, useRef, useState } from "react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { toast } from "sonner";
import { useBranding } from "../context/BrandingContext";
import { Palette, UploadSimple, Trash, FloppyDisk, Plus, ArrowClockwise, ImageSquare, Browser } from "@phosphor-icons/react";

const BACKEND = process.env.REACT_APP_BACKEND_URL;

const ICON_CHOICES = ["truck", "factory", "shield", "chart", "sparkle", "receipt", "users", "package"];

function ScaleControl({ label, description, value, presets, min, max, onChange, testIdPrefix }) {
  const v = Number(value || 1);
  return (
    <div className="border border-slate-200 rounded-lg p-4 bg-slate-50" data-testid={testIdPrefix}>
      <div className="flex items-center justify-between mb-3">
        <div className="min-w-0">
          <div className="font-semibold text-slate-900 text-sm">{label}</div>
          <div className="text-xs text-slate-500 mt-0.5 truncate">{description}</div>
        </div>
        <div className="font-mono text-xs text-indaco bg-white border border-slate-200 rounded px-2 py-1 flex-shrink-0 ml-2" data-testid={`${testIdPrefix}-value`}>
          ×{v.toFixed(2)}
        </div>
      </div>
      <div className="flex items-center gap-1.5 mb-3">
        {presets.map(opt => {
          const active = Math.abs(v - opt.v) < 0.01;
          return (
            <button
              key={opt.v}
              type="button"
              onClick={() => onChange(opt.v)}
              data-testid={`${testIdPrefix}-${opt.lbl.toLowerCase()}`}
              className={`flex-1 py-1.5 px-2 rounded-md text-sm font-semibold transition-all border ${active ? "bg-indaco text-white border-indaco" : "bg-white text-slate-700 border-slate-200 hover:border-indaco/50"}`}
            >
              {opt.lbl}
            </button>
          );
        })}
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={0.05}
        value={v}
        onChange={e => onChange(parseFloat(e.target.value))}
        className="w-full accent-indaco"
        data-testid={`${testIdPrefix}-slider`}
      />
      <div className="flex justify-between text-[10px] text-slate-400 font-mono mt-1">
        <span>{min.toFixed(2)}×</span>
        <span>{((min + max) / 2).toFixed(2)}×</span>
        <span>{max.toFixed(2)}×</span>
      </div>
    </div>
  );
}

function ColorField({ label, value, onChange, testId }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <div className="flex items-center gap-2">
        <input
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-12 h-10 rounded border border-slate-300 cursor-pointer"
          data-testid={`${testId}-picker`}
        />
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="font-mono"
          maxLength={7}
          data-testid={`${testId}-hex`}
        />
      </div>
    </div>
  );
}

function ImageUploader({ kind, title, description, currentUrl, onUploaded, onDeleted, accept }) {
  const [busy, setBusy] = useState(false);
  const ref = useRef(null);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const { data } = await api.post(`/admin/branding/upload/${kind}`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(`${title} caricato (${(data.size / 1024).toFixed(1)} KB · ${data.width}×${data.height})`);
      onUploaded?.();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Upload fallito");
    } finally {
      setBusy(false);
      if (ref.current) ref.current.value = "";
    }
  };

  const handleDelete = async () => {
    if (!window.confirm(`Rimuovere ${title.toLowerCase()}?`)) return;
    try {
      await api.delete(`/admin/branding/image/${kind}`);
      toast.success(`${title} rimosso`);
      onDeleted?.();
    } catch (err) {
      toast.error("Eliminazione fallita");
    }
  };

  return (
    <div className="border border-slate-200 rounded-lg p-4 bg-white" data-testid={`branding-upload-${kind}`}>
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="font-semibold text-slate-900">{title}</div>
          <div className="text-xs text-slate-500 mt-0.5">{description}</div>
        </div>
        {currentUrl && (
          <button
            onClick={handleDelete}
            className="text-red-500 hover:text-red-700 text-xs flex items-center gap-1"
            data-testid={`branding-delete-${kind}`}
          >
            <Trash size={14} /> Rimuovi
          </button>
        )}
      </div>
      <div className="flex items-center gap-4">
        <div className={`flex-shrink-0 w-24 h-24 rounded border-2 border-dashed border-slate-200 flex items-center justify-center overflow-hidden ${kind === 'hero' ? 'bg-slate-900' : 'bg-slate-50'}`}>
          {currentUrl ? (
            <img src={`${BACKEND}${currentUrl}?t=${Date.now()}`} alt={title} className="max-w-full max-h-full object-contain" />
          ) : (
            <ImageSquare size={32} className="text-slate-300" />
          )}
        </div>
        <div className="flex-1">
          <input
            ref={ref}
            type="file"
            accept={accept}
            onChange={handleUpload}
            className="hidden"
            id={`upload-${kind}`}
            data-testid={`branding-file-${kind}`}
          />
          <label htmlFor={`upload-${kind}`}>
            <Button asChild type="button" variant="outline" disabled={busy} className="cursor-pointer" data-testid={`branding-upload-btn-${kind}`}>
              <span><UploadSimple size={16} className="mr-2" />{busy ? "Caricamento…" : "Scegli file"}</span>
            </Button>
          </label>
          <div className="text-[11px] text-slate-400 mt-2 font-mono">Max 8MB · Auto-ridimensionato · Convertito in {kind === "favicon" ? "PNG 96×96" : "WebP"}</div>
        </div>
      </div>
    </div>
  );
}

export default function Branding() {
  const { branding: current, reload } = useBranding();
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [imgVersion, setImgVersion] = useState(0);

  const fetchBranding = useCallback(async () => {
    try {
      const { data } = await api.get("/admin/branding");
      setForm(data);
    } catch (e) {
      toast.error("Caricamento branding fallito");
    }
  }, []);

  useEffect(() => { fetchBranding(); }, [fetchBranding]);

  // Live preview: apply color CSS vars while editing
  useEffect(() => {
    if (!form) return;
    const root = document.documentElement;
    const prev = {
      indaco: root.style.getPropertyValue("--indaco"),
      celeste: root.style.getPropertyValue("--celeste"),
      azzurro: root.style.getPropertyValue("--azzurro"),
      logo: root.style.getPropertyValue("--logo-scale"),
      text: root.style.getPropertyValue("--text-scale"),
    };
    if (form.primary_color) root.style.setProperty("--indaco", form.primary_color);
    if (form.accent_color) root.style.setProperty("--celeste", form.accent_color);
    if (form.dark_color) root.style.setProperty("--azzurro", form.dark_color);
    if (form.logo_scale) root.style.setProperty("--logo-scale", String(form.logo_scale));
    if (form.text_scale) root.style.setProperty("--text-scale", String(form.text_scale));
    return () => {
      if (prev.indaco) root.style.setProperty("--indaco", prev.indaco);
      if (prev.celeste) root.style.setProperty("--celeste", prev.celeste);
      if (prev.azzurro) root.style.setProperty("--azzurro", prev.azzurro);
      if (prev.logo) root.style.setProperty("--logo-scale", prev.logo);
      if (prev.text) root.style.setProperty("--text-scale", prev.text);
    };
  }, [form?.primary_color, form?.accent_color, form?.dark_color, form?.logo_scale, form?.text_scale]);

  if (!form) return <div className="text-slate-400 font-mono text-sm">Caricamento branding…</div>;

  const update = (k, v) => setForm({ ...form, [k]: v });

  const updateFeature = (idx, k, v) => {
    const next = [...(form.login_features || [])];
    next[idx] = { ...next[idx], [k]: v };
    update("login_features", next);
  };
  const addFeature = () => update("login_features", [...(form.login_features || []), { icon: "sparkle", label: "Nuova feature" }]);
  const removeFeature = (idx) => update("login_features", (form.login_features || []).filter((_, i) => i !== idx));

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/admin/branding", {
        app_name: form.app_name,
        tagline: form.tagline,
        login_eyebrow: form.login_eyebrow,
        login_title: form.login_title,
        login_subtitle: form.login_subtitle,
        login_footer: form.login_footer,
        login_features: form.login_features,
        primary_color: form.primary_color,
        accent_color: form.accent_color,
        dark_color: form.dark_color,
        logo_scale: form.logo_scale,
        text_scale: form.text_scale,
      });
      toast.success("Branding salvato");
      await reload();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Salvataggio fallito");
    } finally {
      setSaving(false);
    }
  };

  const onAssetChanged = async () => {
    await fetchBranding();
    await reload();
    setImgVersion(v => v + 1);
  };

  const heroKey = `hero-${imgVersion}`;
  const heroUrl = form.hero_url ? `${BACKEND}${form.hero_url}?v=${imgVersion}` : null;

  return (
    <div className="space-y-6" data-testid="branding-page">
      <PageHeader
        eyebrow="Superadmin"
        title="Branding & estetica"
        subtitle="Personalizza logo, immagini, testi e colori di tutta la piattaforma. Le modifiche sono immediate per tutti i clienti."
        actions={
          <Button onClick={save} disabled={saving} className="bg-indaco hover:bg-indaco-dark" data-testid="branding-save-btn">
            <FloppyDisk size={16} className="mr-2" />{saving ? "Salvataggio…" : "Salva modifiche"}
          </Button>
        }
      />

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* LEFT: settings */}
        <div className="xl:col-span-2 space-y-6">
          {/* Identity */}
          <section className="kpi-card">
            <h3 className="font-display text-lg font-bold mb-4 flex items-center gap-2"><Browser size={20} className="text-indaco" />Identità applicazione</h3>
            <div className="grid grid-cols-2 gap-4">
              <div><Label>Nome applicazione</Label><Input value={form.app_name || ""} onChange={e => update("app_name", e.target.value)} data-testid="branding-app-name" /></div>
              <div><Label>Payoff / Tagline</Label><Input value={form.tagline || ""} onChange={e => update("tagline", e.target.value)} data-testid="branding-tagline" /></div>
            </div>
          </section>

          {/* Images */}
          <section className="kpi-card">
            <h3 className="font-display text-lg font-bold mb-4 flex items-center gap-2"><ImageSquare size={20} className="text-indaco" />Immagini</h3>
            <div className="space-y-4">
              <ImageUploader kind="hero" title="Immagine login (hero a sinistra)" description="L'immagine grande sul pannello blu del login. Consigliato 1920×1200px."
                currentUrl={form.hero_url} onUploaded={onAssetChanged} onDeleted={onAssetChanged}
                accept="image/png,image/jpeg,image/webp" />
              <ImageUploader kind="logo" title="Logo (sidebar + login)" description="Logo rettangolare. Se vuoto, viene usato il nome applicazione con icona Sparkle."
                currentUrl={form.logo_url} onUploaded={onAssetChanged} onDeleted={onAssetChanged}
                accept="image/png,image/jpeg,image/webp,image/svg+xml" />

              {/* Scale controls — independent for logo and text */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="branding-scale-controls">
                <ScaleControl
                  label="Dimensione logo"
                  description="Box logo in sidebar + hero login"
                  testIdPrefix="branding-logo-scale"
                  value={form.logo_scale}
                  min={0.8}
                  max={3.0}
                  presets={[{v:1.0,lbl:"S"},{v:1.25,lbl:"M"},{v:1.5,lbl:"L"},{v:2.0,lbl:"XL"}]}
                  onChange={v => update("logo_scale", v)}
                />
                <ScaleControl
                  label="Dimensione testi brand"
                  description="Nome applicazione + sottotitolo"
                  testIdPrefix="branding-text-scale"
                  value={form.text_scale}
                  min={0.8}
                  max={2.5}
                  presets={[{v:1.0,lbl:"S"},{v:1.15,lbl:"M"},{v:1.3,lbl:"L"},{v:1.6,lbl:"XL"}]}
                  onChange={v => update("text_scale", v)}
                />
              </div>

              <ImageUploader kind="favicon" title="Favicon (tab browser)" description="Icona tab del browser. Viene forzata a PNG 96×96. Accettati PNG/ICO/JPG."
                currentUrl={form.favicon_url} onUploaded={onAssetChanged} onDeleted={onAssetChanged}
                accept="image/png,image/x-icon,image/vnd.microsoft.icon,image/jpeg,image/webp" />
            </div>
          </section>

          {/* Texts */}
          <section className="kpi-card">
            <h3 className="font-display text-lg font-bold mb-4 flex items-center gap-2"><ArrowClockwise size={20} className="text-indaco" />Testi pagina login</h3>
            <div className="grid grid-cols-1 gap-4">
              <div><Label>Eyebrow (sopra il titolo)</Label><Input value={form.login_eyebrow || ""} onChange={e => update("login_eyebrow", e.target.value)} data-testid="branding-login-eyebrow" /></div>
              <div><Label>Titolo principale</Label><Input value={form.login_title || ""} onChange={e => update("login_title", e.target.value)} data-testid="branding-login-title" /></div>
              <div><Label>Sottotitolo / descrizione</Label><Textarea rows={3} value={form.login_subtitle || ""} onChange={e => update("login_subtitle", e.target.value)} data-testid="branding-login-subtitle" /></div>
              <div><Label>Footer (copyright)</Label><Input value={form.login_footer || ""} onChange={e => update("login_footer", e.target.value)} data-testid="branding-login-footer" /></div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <Label>Feature cards (max 6)</Label>
                  <Button type="button" size="sm" variant="outline" onClick={addFeature} disabled={(form.login_features || []).length >= 6} data-testid="branding-add-feature">
                    <Plus size={14} className="mr-1" />Aggiungi
                  </Button>
                </div>
                <div className="space-y-2">
                  {(form.login_features || []).map((f, idx) => (
                    <div key={idx} className="flex gap-2 items-center" data-testid={`branding-feature-${idx}`}>
                      <select
                        value={f.icon}
                        onChange={e => updateFeature(idx, "icon", e.target.value)}
                        className="h-9 px-2 border border-slate-300 rounded-md text-sm font-mono bg-white"
                      >
                        {ICON_CHOICES.map(ic => <option key={ic} value={ic}>{ic}</option>)}
                      </select>
                      <Input value={f.label} onChange={e => updateFeature(idx, "label", e.target.value)} className="flex-1" />
                      <button type="button" onClick={() => removeFeature(idx)} className="text-red-500 hover:text-red-700" data-testid={`branding-remove-feature-${idx}`}>
                        <Trash size={16} />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </section>

          {/* Colors */}
          <section className="kpi-card">
            <h3 className="font-display text-lg font-bold mb-4 flex items-center gap-2"><Palette size={20} className="text-indaco" />Colori brand</h3>
            <div className="grid grid-cols-3 gap-4">
              <ColorField label="Primario (pulsanti, link)" value={form.primary_color} onChange={v => update("primary_color", v)} testId="branding-primary" />
              <ColorField label="Accento (hover, badge)" value={form.accent_color} onChange={v => update("accent_color", v)} testId="branding-accent" />
              <ColorField label="Dark (sfondo hero)" value={form.dark_color} onChange={v => update("dark_color", v)} testId="branding-dark" />
            </div>
            <div className="text-xs text-slate-500 mt-3 font-mono">I colori vengono applicati via CSS variable (--indaco, --celeste, --azzurro). Non serve ricaricare la pagina.</div>
          </section>
        </div>

        {/* RIGHT: preview */}
        <div className="xl:col-span-1">
          <div className="sticky top-6 space-y-4">
            <div className="kpi-card">
              <div className="overline mb-2">Anteprima login</div>
              <div className="rounded-lg overflow-hidden border border-slate-200 aspect-[3/4] relative" style={{ backgroundColor: form.dark_color || "#0f172a" }}>
                {heroUrl && (
                  <img src={heroUrl} alt="hero preview" className="absolute inset-0 w-full h-full object-cover opacity-30" key={heroKey} />
                )}
                <div className="absolute inset-0" style={{ background: `linear-gradient(to bottom right, ${form.primary_color}99, #0f172aDD)` }} />
                <div className="relative z-10 p-4 flex flex-col justify-between h-full text-white">
                  <div>
                    <div className="text-[10px] font-mono uppercase tracking-widest" style={{ color: form.accent_color }}>{form.login_eyebrow}</div>
                    <div className="font-bold text-sm mt-1 leading-tight">{form.login_title}</div>
                    <div className="text-[10px] text-slate-300 mt-2 line-clamp-3">{form.login_subtitle}</div>
                  </div>
                  <div className="grid grid-cols-2 gap-1">
                    {(form.login_features || []).slice(0, 4).map((f, i) => (
                      <div key={i} className="bg-white/10 border border-white/20 rounded px-1.5 py-1 text-[9px] font-medium truncate">{f.label}</div>
                    ))}
                  </div>
                </div>
              </div>
              <div className="text-[11px] text-slate-500 mt-3 font-mono">Preview in tempo reale · Salva per applicare a tutti</div>
            </div>

            <div className="kpi-card">
              <div className="overline mb-2">Palette corrente</div>
              <div className="space-y-2">
                {[
                  { k: "primary_color", label: "Primario" },
                  { k: "accent_color", label: "Accento" },
                  { k: "dark_color", label: "Dark" },
                ].map(({ k, label }) => (
                  <div key={k} className="flex items-center gap-3 text-xs">
                    <div className="w-8 h-8 rounded border border-slate-200" style={{ backgroundColor: form[k] }} />
                    <div className="flex-1">
                      <div className="font-semibold">{label}</div>
                      <div className="font-mono text-slate-500">{form[k]}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
