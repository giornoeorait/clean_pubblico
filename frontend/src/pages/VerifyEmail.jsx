import React, { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import api from "../lib/api";
import { CheckCircle, XCircle, Sparkle, CircleNotch } from "@phosphor-icons/react";

export default function VerifyEmail() {
  const [sp] = useSearchParams();
  const [status, setStatus] = useState("checking"); // checking | success | error
  const [message, setMessage] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    const token = sp.get("token");
    if (!token) { setStatus("error"); setMessage("Link non valido (manca il token)"); return; }
    api.post("/auth/verify-email", { token })
      .then(({ data }) => { setStatus("success"); setMessage(`Email ${data.email} verificata correttamente`); })
      .catch((e) => { setStatus("error"); setMessage(e.response?.data?.detail || "Errore verifica"); });
  }, [sp]);

  const Icon = status === "success" ? CheckCircle : status === "error" ? XCircle : CircleNotch;
  const color = status === "success" ? "text-emerald-500" : status === "error" ? "text-red-500" : "text-indaco";

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl p-10 max-w-md w-full text-center">
        <div className="flex items-center justify-center gap-2 mb-6">
          <div className="w-10 h-10 rounded-md bg-gradient-to-br from-azzurro to-indaco flex items-center justify-center">
            <Sparkle size={22} weight="fill" className="text-white" />
          </div>
          <div className="font-display font-bold text-2xl">CleanTec</div>
        </div>
        <Icon size={64} weight={status === "checking" ? "regular" : "fill"} className={`mx-auto mb-4 ${color} ${status === "checking" ? "animate-spin" : ""}`} />
        <h1 className="font-display text-2xl font-bold mb-2">
          {status === "checking" ? "Verifica in corso…" : status === "success" ? "Tutto fatto!" : "Link non valido"}
        </h1>
        <p className="text-slate-600 mb-6">{message}</p>
        {status === "success" ? (
          <button onClick={() => navigate("/dashboard")} className="w-full bg-indaco hover:bg-indaco-dark text-white py-3 rounded-md font-semibold" data-testid="verify-continue-btn">
            Vai alla dashboard
          </button>
        ) : status === "error" ? (
          <Link to="/login" className="inline-block text-indaco font-semibold hover:underline">Torna al login</Link>
        ) : null}
      </div>
    </div>
  );
}
