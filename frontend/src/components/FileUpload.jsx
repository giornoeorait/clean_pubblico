import React, { useRef, useState } from "react";
import api, { BACKEND_URL } from "../lib/api";
import { Camera, X, PaperPlaneTilt, Paperclip } from "@phosphor-icons/react";
import { toast } from "sonner";

/**
 * FileUpload — accepts multiple images, uploads each file to /api/files/upload,
 * returns array of {id, storage_path, url, original_filename} via onChange.
 * Shows thumbnails with remove button.
 */
export default function FileUpload({ value = [], onChange, context = "misc", accept = "image/*", label = "Carica foto", testId = "file-upload" }) {
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);

  const token = typeof window !== "undefined" ? localStorage.getItem("cleantec_token") : "";

  const handleFiles = async (files) => {
    if (!files?.length) return;
    setBusy(true);
    const next = [...value];
    for (const f of files) {
      try {
        const form = new FormData();
        form.append("file", f);
        const { data } = await api.post(`/files/upload?context=${encodeURIComponent(context)}`, form, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        next.push(data);
      } catch (e) {
        toast.error(e.response?.data?.detail || `Upload fallito: ${f.name}`);
      }
    }
    onChange && onChange(next);
    setBusy(false);
    if (inputRef.current) inputRef.current.value = "";
  };

  const remove = (i) => {
    const next = value.filter((_, idx) => idx !== i);
    onChange && onChange(next);
  };

  return (
    <div data-testid={testId}>
      <div className="flex items-center gap-2 mb-2">
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={busy}
          className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-semibold text-indaco bg-indaco/10 hover:bg-indaco/20 border border-indaco/20 rounded-md disabled:opacity-50"
          data-testid={`${testId}-btn`}
        >
          <Camera size={14} weight="duotone" />
          {busy ? "Caricamento…" : label}
        </button>
        <span className="text-xs text-slate-400">{value.length} file</span>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple
        className="hidden"
        onChange={(e) => handleFiles(Array.from(e.target.files || []))}
        data-testid={`${testId}-input`}
      />
      {value.length > 0 && (
        <div className="grid grid-cols-4 md:grid-cols-6 gap-2">
          {value.map((f, i) => {
            const src = `${BACKEND_URL}${f.url}?auth=${token}`;
            const isImg = (f.content_type || "").startsWith("image/");
            return (
              <div key={f.id || i} className="relative group">
                {isImg ? (
                  <img src={src} alt={f.original_filename} className="w-full h-20 object-cover rounded border border-slate-200" />
                ) : (
                  <div className="w-full h-20 rounded border border-slate-200 flex items-center justify-center bg-slate-50">
                    <Paperclip size={20} className="text-slate-400" />
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => remove(i)}
                  className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-red-500 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 shadow"
                >
                  <X size={12} weight="bold" />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
