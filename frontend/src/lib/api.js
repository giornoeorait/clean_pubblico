import axios from "axios";

export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const api = axios.create({
  baseURL: API,
  headers: { "Content-Type": "application/json" },
});

// Attach token from localStorage fallback
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("cleantec_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Intercept 402 (quota/subscription expired) globally
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 402) {
      // Lazy-import to avoid circular deps
      import("sonner").then(({ toast }) => {
        toast.error(err.response?.data?.detail || "Limite piano raggiunto", {
          action: { label: "Aggiorna piano", onClick: () => { window.location.href = "/billing"; } },
          duration: 7000,
        });
      });
    }
    return Promise.reject(err);
  }
);

export default api;

export function formatApiErrorDetail(detail) {
  if (detail == null) return "Errore inatteso. Riprova.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail
      .map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e)))
      .filter(Boolean)
      .join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}
