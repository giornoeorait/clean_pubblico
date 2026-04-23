import React, { useEffect, useRef, useState } from "react";
import api, { BACKEND_URL } from "../lib/api";
import { PencilSimpleLine, CheckCircle, ArrowCounterClockwise } from "@phosphor-icons/react";
import { toast } from "sonner";

/**
 * SignaturePad — HTML canvas capturing a signature, uploads as PNG to /api/files/signature.
 * Returns the uploaded record via onSaved (or reads initial from `value`).
 */
export default function SignaturePad({ value, onSaved, context = "signature", testId = "signature-pad" }) {
  const canvasRef = useRef(null);
  const [drawing, setDrawing] = useState(false);
  const [hasInk, setHasInk] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(value || null);

  const token = typeof window !== "undefined" ? localStorage.getItem("cleantec_token") : "";

  useEffect(() => {
    const c = canvasRef.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    ctx.lineWidth = 2.5;
    ctx.lineCap = "round";
    ctx.strokeStyle = "#0F172A";
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, c.width, c.height);
  }, []);

  const getPos = (e) => {
    const c = canvasRef.current;
    const rect = c.getBoundingClientRect();
    const scaleX = c.width / rect.width;
    const scaleY = c.height / rect.height;
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    return { x: (clientX - rect.left) * scaleX, y: (clientY - rect.top) * scaleY };
  };

  const start = (e) => {
    e.preventDefault();
    setDrawing(true);
    const { x, y } = getPos(e);
    const ctx = canvasRef.current.getContext("2d");
    ctx.beginPath();
    ctx.moveTo(x, y);
  };
  const move = (e) => {
    if (!drawing) return;
    e.preventDefault();
    const { x, y } = getPos(e);
    const ctx = canvasRef.current.getContext("2d");
    ctx.lineTo(x, y);
    ctx.stroke();
    setHasInk(true);
  };
  const end = () => setDrawing(false);

  const clear = () => {
    const c = canvasRef.current;
    const ctx = c.getContext("2d");
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, c.width, c.height);
    setHasInk(false);
  };

  const save = async () => {
    if (!hasInk) { toast.error("Firma vuota"); return; }
    setSaving(true);
    try {
      const dataUrl = canvasRef.current.toDataURL("image/png");
      const { data } = await api.post("/files/signature", { data_url: dataUrl, context });
      setSaved(data);
      onSaved && onSaved(data);
      toast.success("Firma registrata");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore salvataggio firma");
    }
    setSaving(false);
  };

  if (saved) {
    const src = `${BACKEND_URL}${saved.url}?auth=${token}`;
    return (
      <div data-testid={testId}>
        <div className="border border-slate-200 rounded-md p-2 bg-white">
          <img src={src} alt="Firma" className="max-h-24 object-contain" />
        </div>
        <button
          type="button"
          onClick={() => { setSaved(null); setHasInk(false); setTimeout(clear, 50); }}
          className="mt-2 text-xs text-slate-500 hover:text-indaco inline-flex items-center gap-1"
          data-testid={`${testId}-reset`}
        >
          <ArrowCounterClockwise size={12} /> Rifai firma
        </button>
      </div>
    );
  }

  return (
    <div data-testid={testId}>
      <div className="relative border-2 border-dashed border-slate-300 rounded-md bg-white">
        <canvas
          ref={canvasRef}
          width={600}
          height={180}
          className="w-full h-32 touch-none cursor-crosshair"
          onMouseDown={start} onMouseMove={move} onMouseUp={end} onMouseLeave={end}
          onTouchStart={start} onTouchMove={move} onTouchEnd={end}
          data-testid={`${testId}-canvas`}
        />
        {!hasInk && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none text-slate-300 text-sm">
            <PencilSimpleLine size={18} className="mr-2" /> Firma qui
          </div>
        )}
      </div>
      <div className="flex gap-2 mt-2">
        <button
          type="button" onClick={clear}
          className="text-xs px-3 py-1.5 bg-slate-100 hover:bg-slate-200 rounded-md flex items-center gap-1"
          data-testid={`${testId}-clear`}
        >
          <ArrowCounterClockwise size={12} /> Pulisci
        </button>
        <button
          type="button" onClick={save} disabled={!hasInk || saving}
          className="text-xs px-3 py-1.5 bg-indaco hover:bg-indaco-dark text-white rounded-md flex items-center gap-1 disabled:opacity-50"
          data-testid={`${testId}-save`}
        >
          <CheckCircle size={12} weight="bold" /> {saving ? "Salvataggio…" : "Salva firma"}
        </button>
      </div>
    </div>
  );
}
