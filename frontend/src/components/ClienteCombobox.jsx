import React, { useMemo, useState } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "./ui/command";
import { Button } from "./ui/button";
import { CaretUpDown, Check } from "@phosphor-icons/react";
import { clientePrimary, clienteSecondary } from "../lib/clienteLabel";

/**
 * Combobox cliente con campo di ricerca.
 * - Elenco ordinato alfabeticamente per denominazione_struttura / ragione_sociale
 * - Filtra al volo per nome cliente / struttura
 *
 * Props:
 *   clienti: lista clienti (filtrati attivi a carico del parent o no)
 *   value: cliente_id selezionato
 *   onChange: (cliente_id) => void
 *   disabled?: boolean
 *   placeholder?: string
 *   showListinoBadge?: bool   // se true mostra '• listino ✓' / '• no listino'
 *   testId?: string
 */
export default function ClienteCombobox({
  clienti = [],
  value,
  onChange,
  disabled = false,
  placeholder = "Seleziona cliente…",
  showListinoBadge = false,
  allowAll = false,           // se true mostra opzione "Tutti i clienti" con value="all"
  allLabel = "Tutti i clienti",
  testId = "cliente-combobox",
}) {
  const [open, setOpen] = useState(false);

  const sorted = useMemo(() => {
    const arr = [...clienti];
    arr.sort((a, b) => {
      const A = (a.denominazione_struttura || a.ragione_sociale || "").toLowerCase();
      const B = (b.denominazione_struttura || b.ragione_sociale || "").toLowerCase();
      return A.localeCompare(B, "it");
    });
    return arr;
  }, [clienti]);

  const selected = sorted.find(c => c.id === value);
  const isAll = allowAll && value === "all";

  return (
    <Popover open={open} onOpenChange={(v) => !disabled && setOpen(v)}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          disabled={disabled}
          data-testid={testId}
          className="w-full justify-between font-normal h-10 px-3 bg-white"
        >
          <span className="truncate text-left">
            {isAll ? (
              <span className="font-medium">{allLabel}</span>
            ) : selected ? (
              <>
                <span className="font-medium">{clientePrimary(selected)}</span>
                {clienteSecondary(selected) && <span className="text-slate-500"> · {clienteSecondary(selected)}</span>}
              </>
            ) : (
              <span className="text-slate-400">{placeholder}</span>
            )}
          </span>
          <CaretUpDown size={14} className="opacity-50 ml-2 flex-shrink-0" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="p-0 w-[--radix-popover-trigger-width] min-w-[320px]"
        align="start"
      >
        <Command
          filter={(rawValue, search) => {
            // 'rawValue' è la stringa che mettiamo in CommandItem.value (full label lowercase).
            // Match case-insensitive sul testo cercato.
            if (!search) return 1;
            const q = search.toLowerCase().trim();
            return rawValue.toLowerCase().includes(q) ? 1 : 0;
          }}
        >
          <CommandInput placeholder="Cerca cliente…" data-testid={`${testId}-search`} />
          <CommandList>
            <CommandEmpty>Nessun cliente trovato.</CommandEmpty>
            <CommandGroup>
              {allowAll && (
                <CommandItem
                  value={allLabel}
                  onSelect={() => {
                    onChange?.("all");
                    setOpen(false);
                  }}
                  className="flex items-center gap-2"
                  data-testid={`${testId}-opt-all`}
                >
                  <Check size={14} className={`flex-shrink-0 ${isAll ? "opacity-100 text-indaco" : "opacity-0"}`} weight="bold" />
                  <span className="font-medium">{allLabel}</span>
                </CommandItem>
              )}
              {sorted.map(c => {
                const primary = clientePrimary(c);
                const secondary = clienteSecondary(c);
                const valueText = `${primary} ${secondary || ""} ${c.partita_iva || ""}`.trim();
                return (
                  <CommandItem
                    key={c.id}
                    value={valueText}
                    onSelect={() => {
                      onChange?.(c.id);
                      setOpen(false);
                    }}
                    className="flex items-start gap-2"
                    data-testid={`${testId}-opt-${c.id}`}
                  >
                    <Check size={14} className={`mt-0.5 flex-shrink-0 ${value === c.id ? "opacity-100 text-indaco" : "opacity-0"}`} weight="bold" />
                    <div className="flex flex-col min-w-0 flex-1">
                      <span className="font-medium truncate">{primary}</span>
                      {secondary && <span className="text-xs text-slate-500 truncate">{secondary}</span>}
                    </div>
                    {showListinoBadge && (
                      <span className={`text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded flex-shrink-0 ${c.listino_id ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
                        {c.listino_id ? "listino" : "no list."}
                      </span>
                    )}
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
