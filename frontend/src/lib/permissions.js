/**
 * Hook per gating UI in base al ruolo utente.
 *
 * canSeePrices = true SOLO per role 'admin' (e superadmin).
 * Tutti gli altri ruoli operativi (contabilita, logistica, operatore, hr, ecc.)
 * vedono SOLO informazioni merce/operative.
 */
import { useAuth } from "../context/AuthContext";

export function usePermissions() {
  const { user } = useAuth() || {};
  const role = user?.role || "";
  const isAdmin = role === "admin" || role === "superadmin";
  return {
    role,
    isAdmin,
    canSeePrices: isAdmin || role === "contabilita",
    canEditDate: isAdmin,
    canSeeRevenue: isAdmin || role === "contabilita",
    canAccessBilling: isAdmin || role === "contabilita",
  };
}

export function useCanSeePrices() {
  return usePermissions().canSeePrices;
}
