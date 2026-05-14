// Centralized label helpers for "cliente" display.
// Convention agreed with user:
//   - Primary label = denominazione_struttura (the actual hotel/site name)
//   - Secondary label (small) = ragione_sociale (legal name of the company)
// If denominazione_struttura is empty, fall back to ragione_sociale only.

export function clientePrimary(c) {
  if (!c) return "—";
  return (c.denominazione_struttura || c.ragione_sociale || "—").trim() || "—";
}

export function clienteSecondary(c) {
  if (!c) return "";
  // Show ragione_sociale as the small line ONLY if denominazione_struttura is present
  if (c.denominazione_struttura && c.ragione_sociale && c.denominazione_struttura.trim() !== c.ragione_sociale.trim()) {
    return c.ragione_sociale;
  }
  return "";
}

// Variant for denormalized docs (DDT/Fatture/Sospesi/Ordinativi snapshot)
// which expose `cliente_nome` (== ragione_sociale at creation) and `cliente_denominazione`.
export function docPrimary(d) {
  if (!d) return "—";
  return (d.cliente_denominazione || d.cliente_nome || "—").trim() || "—";
}

export function docSecondary(d) {
  if (!d) return "";
  if (d.cliente_denominazione && d.cliente_nome && d.cliente_denominazione.trim() !== d.cliente_nome.trim()) {
    return d.cliente_nome;
  }
  return "";
}
