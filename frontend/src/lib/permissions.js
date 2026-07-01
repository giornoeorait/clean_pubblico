/**
 * Hook per gating UI in base a ruolo + matrice di permessi granulari.
 *
 * L'admin (o superadmin) bypassa qualsiasi restrizione.
 * Per gli altri ruoli si usa `user.permissions_resolved` che il backend
 * calcola combinando i default del ruolo con l'override salvato sull'utente.
 */
import { useAuth } from "../context/AuthContext";

export const PERMISSION_SECTIONS = [
  "clienti", "articoli", "listini", "offerte", "ordinativi", "ddt",
  "fatture", "sospesi", "fornitori", "fatture_fornitore", "ddt_ricevuti",
  "costi", "dipendenti", "report",
];

export const SECTION_LABELS = {
  clienti: "Clienti",
  articoli: "Articoli",
  listini: "Listini",
  offerte: "Offerte & Preventivi",
  ordinativi: "Ordinativi",
  ddt: "D.D.T.",
  fatture: "Fatture (Fatturazione)",
  sospesi: "Sospesi",
  fornitori: "Fornitori",
  fatture_fornitore: "Fatture fornitore",
  ddt_ricevuti: "DDT ricevuti",
  costi: "Costi",
  dipendenti: "Dipendenti",
  report: "Report & Statistiche",
};

const _ALL_TRUE = () => Object.fromEntries(PERMISSION_SECTIONS.map(s => [s, { view: true, edit: true }]));
const _ALL_FALSE = () => Object.fromEntries(PERMISSION_SECTIONS.map(s => [s, { view: false, edit: false }]));

/** Restituisce la matrice permessi risolta per un utente. */
export function getResolvedPermissions(user) {
  const role = user?.role || "";
  if (role === "admin" || role === "superadmin") return _ALL_TRUE();
  const p = user?.permissions_resolved;
  if (p && typeof p === "object") {
    // Normalizza: garantisce tutte le sezioni presenti
    const out = _ALL_FALSE();
    for (const s of PERMISSION_SECTIONS) {
      const entry = p[s] || {};
      out[s] = { view: !!entry.view, edit: !!entry.edit };
    }
    return out;
  }
  return _ALL_FALSE();
}

export function usePermissions() {
  const { user } = useAuth() || {};
  const role = user?.role || "";
  const isAdmin = role === "admin" || role === "superadmin";
  const canEditDate = isAdmin || !!user?.can_edit_dates;
  const perms = getResolvedPermissions(user);

  /** true se l'utente può vedere la sezione */
  const canView = (section) => isAdmin || !!perms[section]?.view;
  /** true se l'utente può modificare (creare/modificare/eliminare) nella sezione */
  const canEdit = (section) => isAdmin || !!perms[section]?.edit;

  return {
    role,
    isAdmin,
    // Legacy / retro-compatibilità
    canSeePrices: isAdmin || role === "contabilita",
    canEditDate,
    canEditDDTDate: canEditDate,
    canSeeRevenue: isAdmin || role === "contabilita",
    canAccessBilling: isAdmin || role === "contabilita",
    // Granulari
    permissions: perms,
    canView,
    canEdit,
  };
}

export function useCanSeePrices() {
  return usePermissions().canSeePrices;
}
