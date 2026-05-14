"""Import wizard: bulk insert anagrafiche da file Excel/CSV.

Endpoints (admin/contabilita only):
  POST /api/imports/clienti/preview  — parse multipart file, return rows + status badges
  POST /api/imports/clienti/commit   — insert validated rows into MongoDB

Behavior:
  - Auto-detect the header row (the first row containing 'Ragione Sociale' or 'P IVA').
  - Dedupe by (partita_iva + denominazione_struttura) against existing tenant clienti.
  - Fill missing required fields with placeholders so partial rows still import.
"""
from __future__ import annotations

import io
import re
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel

from core import db, new_id, now_utc, require_roles, tenant_id_of, log_audit

router = APIRouter(prefix="/imports", tags=["imports"])

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_ROWS = 2000

# Excel header → ClienteIn field mapping
HEADER_ALIASES: Dict[str, List[str]] = {
    "denominazione_struttura":  ["name", "denominazione", "denominazione struttura", "struttura"],
    "referente":                ["nome cliente", "nome contatto", "referente", "contact name"],
    "ragione_sociale":          ["ragione sociale", "ragione_sociale", "company name", "azienda"],
    "indirizzo":                ["indirizzo fatturazione", "indirizzo", "billing address", "sede legale"],
    "cap":                      ["cap", "postal code", "zip"],
    "indirizzo_scarico":        ["indirizzo di scarico", "indirizzo scarico", "discharge address", "scarico"],
    "partita_iva":              ["p iva", "p.iva", "piva", "partita iva", "vat", "p-iva"],
    "codice_fiscale":           ["iban/ cod fiscale", "iban/cod fiscale", "codice fiscale", "cod fiscale", "cf", "iban"],
    "codice_sdi":               ["cod sdi", "codice sdi", "sdi", "codice destinatario"],
    "pec":                      ["pec", "certified email"],
    "telefono":                 ["company phone", "telefono", "phone", "tel"],
    "email":                    ["contact email", "email", "mail", "e-mail"],
    "note":                     ["note", "notes", "annotazioni"],
}


# ---------------- Parsing helpers ----------------

def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _map_headers(headers: List[Any]) -> Dict[int, str]:
    """Return {column_index: field_name} based on alias matching."""
    mapping: Dict[int, str] = {}
    for idx, h in enumerate(headers):
        nh = _norm(h)
        if not nh:
            continue
        for field, aliases in HEADER_ALIASES.items():
            if nh in aliases:
                mapping[idx] = field
                break
    return mapping


def _read_xlsx(blob: bytes) -> List[List[Any]]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(blob), data_only=True, read_only=True)
    ws = wb.active
    rows: List[List[Any]] = []
    for row in ws.iter_rows(values_only=True):
        rows.append(list(row))
        if len(rows) > MAX_ROWS + 50:
            break
    wb.close()
    return rows


def _read_csv(blob: bytes) -> List[List[Any]]:
    import csv
    # Try utf-8 first then fallback to latin-1
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = blob.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise HTTPException(400, "Encoding CSV non riconosciuto")
    # Sniff delimiter
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except Exception:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect=dialect)
    return [row for row in reader][: MAX_ROWS + 50]


def _find_header_row(rows: List[List[Any]]) -> int:
    """Find first row that looks like a header (contains 'ragione sociale' or 'p iva')."""
    needles = {"ragione sociale", "p iva", "p.iva", "partita iva", "name"}
    for idx, row in enumerate(rows[:30]):
        normalised = {_norm(c) for c in row if c is not None}
        if normalised & needles:
            return idx
    raise HTTPException(400, "Intestazione del file non riconosciuta. "
                             "Assicurati che contenga almeno una colonna 'Ragione Sociale' o 'P IVA'.")


def _cell_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


# ---------------- Row → cliente dict ----------------

PLACEHOLDER_EMAIL = "noemail@import.local"
PLACEHOLDER_TELEFONO = "0"
PLACEHOLDER_INDIRIZZO = "—"


def _build_cliente(row: List[Any], mapping: Dict[int, str]) -> Dict[str, Any]:
    raw = {field: "" for field in HEADER_ALIASES.keys()}
    for idx, field in mapping.items():
        if idx < len(row):
            raw[field] = _cell_str(row[idx])

    # Fold CAP into indirizzo if available and not already in it
    indirizzo = raw["indirizzo"]
    cap = raw["cap"]
    if cap and cap not in indirizzo:
        indirizzo = f"{cap} {indirizzo}".strip()

    # Compose note from "referente" + existing note
    note_parts = []
    if raw["referente"]:
        note_parts.append(f"Referente: {raw['referente']}")
    if raw["note"]:
        note_parts.append(raw["note"])
    note = " · ".join(note_parts)

    # Strip phone leading "+" and whitespace; keep as string
    telefono = re.sub(r"\s+", "", raw["telefono"])
    email = raw["email"].lower()

    cliente = {
        "denominazione_struttura": raw["denominazione_struttura"],
        "ragione_sociale":         raw["ragione_sociale"] or raw["denominazione_struttura"],
        "partita_iva":             re.sub(r"\D+", "", raw["partita_iva"]),
        "codice_fiscale":          raw["codice_fiscale"],
        "indirizzo":               indirizzo or PLACEHOLDER_INDIRIZZO,
        "indirizzo_scarico":       raw["indirizzo_scarico"],
        "email":                   email or PLACEHOLDER_EMAIL,
        "pec":                     raw["pec"],
        "codice_sdi":              raw["codice_sdi"],
        "telefono":                telefono or PLACEHOLDER_TELEFONO,
        "tipologia":               "hotel",
        "condizioni_pagamento":    "30gg",
        "giorni_ritiro":           [],
        "note":                    note,
        "attivo":                  True,
    }

    # Track which placeholders were applied (for UI badge)
    placeholders: List[str] = []
    if cliente["email"] == PLACEHOLDER_EMAIL:
        placeholders.append("email")
    if cliente["telefono"] == PLACEHOLDER_TELEFONO:
        placeholders.append("telefono")
    if cliente["indirizzo"] == PLACEHOLDER_INDIRIZZO:
        placeholders.append("indirizzo")
    if not cliente["ragione_sociale"]:
        placeholders.append("ragione_sociale")
    if not cliente["partita_iva"]:
        placeholders.append("partita_iva")
    cliente["_placeholders"] = placeholders
    return cliente


# ---------------- Endpoints ----------------


@router.post("/clienti/preview")
async def preview_clienti(file: UploadFile = File(...),
                          user: Dict = Depends(require_roles("admin", "contabilita"))):
    """Parse the uploaded file and return per-row status (ok/warning/duplicate)."""
    blob = await file.read()
    if not blob:
        raise HTTPException(400, "File vuoto")
    if len(blob) > MAX_FILE_SIZE:
        raise HTTPException(400, f"File troppo grande (max {MAX_FILE_SIZE // 1024 // 1024} MB)")

    fname = (file.filename or "").lower()
    if fname.endswith(".csv"):
        rows = _read_csv(blob)
    elif fname.endswith(".xlsx") or fname.endswith(".xls") or fname.endswith(".xlsm"):
        rows = _read_xlsx(blob)
    else:
        raise HTTPException(400, "Formato non supportato. Usa .xlsx, .xls o .csv")

    if not rows:
        raise HTTPException(400, "File vuoto o non leggibile")

    header_idx = _find_header_row(rows)
    headers = rows[header_idx]
    mapping = _map_headers(headers)
    if not mapping:
        raise HTTPException(400, "Nessuna colonna riconosciuta nell'intestazione")

    data_rows = rows[header_idx + 1:]
    if len(data_rows) > MAX_ROWS:
        raise HTTPException(400, f"Troppi record (max {MAX_ROWS})")

    # Load existing clienti for duplicate detection
    tid = tenant_id_of(user)
    existing = await db.clienti.find(
        {"tenant_id": tid},
        {"_id": 0, "id": 1, "partita_iva": 1, "denominazione_struttura": 1, "ragione_sociale": 1},
    ).to_list(100000)
    existing_keys = set()
    for c in existing:
        key = (
            (c.get("partita_iva") or "").strip(),
            (c.get("denominazione_struttura") or c.get("ragione_sociale") or "").strip().lower(),
        )
        existing_keys.add(key)

    parsed: List[Dict[str, Any]] = []
    seen_in_file: set = set()
    for ridx, row in enumerate(data_rows, start=header_idx + 2):
        if not any((c is not None and str(c).strip()) for c in row):
            continue  # skip blank
        cliente = _build_cliente(row, mapping)
        key = (cliente["partita_iva"], (cliente["denominazione_struttura"] or cliente["ragione_sociale"]).strip().lower())

        status = "ok"
        reasons: List[str] = []

        if not cliente["partita_iva"] and not cliente["ragione_sociale"]:
            status = "skip"
            reasons.append("Mancano sia P.IVA che Ragione Sociale")
        elif key in existing_keys:
            status = "duplicate"
            reasons.append("Già presente in anagrafica")
        elif key in seen_in_file:
            status = "duplicate"
            reasons.append("Duplicato nel file")
        else:
            seen_in_file.add(key)
            if cliente["_placeholders"]:
                status = "warning"
                reasons.append("Placeholder applicato per: " + ", ".join(cliente["_placeholders"]))

        parsed.append({
            "row_number": ridx,
            "status": status,
            "reasons": reasons,
            "cliente": {k: v for k, v in cliente.items() if k != "_placeholders"},
            "placeholders": cliente["_placeholders"],
        })

    counts = {
        "total": len(parsed),
        "ok": sum(1 for p in parsed if p["status"] == "ok"),
        "warning": sum(1 for p in parsed if p["status"] == "warning"),
        "duplicate": sum(1 for p in parsed if p["status"] == "duplicate"),
        "skip": sum(1 for p in parsed if p["status"] == "skip"),
    }
    return {
        "header_row": header_idx + 1,
        "columns_detected": {headers[i] if i < len(headers) else "": f for i, f in mapping.items()},
        "rows": parsed,
        "counts": counts,
    }


class CommitClientiIn(BaseModel):
    clienti: List[Dict[str, Any]]
    # Only rows with these statuses get imported (defaults: ok + warning)
    accept_statuses: List[str] = ["ok", "warning"]


@router.post("/clienti/commit")
async def commit_clienti(body: CommitClientiIn,
                         user: Dict = Depends(require_roles("admin", "contabilita"))):
    """Insert the provided rows into db.clienti, applying tenant scope.

    Each item must include a 'status' field (from the preview) and a 'cliente' object.
    Rows whose status is not in `accept_statuses` are skipped (no DB write).
    """
    tid = tenant_id_of(user)
    accept = set(body.accept_statuses or ["ok", "warning"])

    # Re-check duplicates server-side (defense in depth)
    existing = await db.clienti.find(
        {"tenant_id": tid},
        {"_id": 0, "partita_iva": 1, "denominazione_struttura": 1, "ragione_sociale": 1},
    ).to_list(100000)
    existing_keys = set()
    for c in existing:
        existing_keys.add((
            (c.get("partita_iva") or "").strip(),
            (c.get("denominazione_struttura") or c.get("ragione_sociale") or "").strip().lower(),
        ))

    inserted = 0
    skipped = 0
    seen_in_run: set = set()
    errors: List[Dict[str, Any]] = []

    now = now_utc()
    for item in body.clienti:
        status = (item.get("status") or "").lower()
        cliente = item.get("cliente") or {}
        if status not in accept:
            skipped += 1
            continue
        piva = (cliente.get("partita_iva") or "").strip()
        denom = (cliente.get("denominazione_struttura") or cliente.get("ragione_sociale") or "").strip().lower()
        key = (piva, denom)
        if key in existing_keys or key in seen_in_run:
            skipped += 1
            continue
        seen_in_run.add(key)

        # Build the DB doc (mirror ClienteIn defaults but accept already-shaped dict)
        doc = {
            "id": new_id(),
            "tenant_id": tid,
            "created_at": now,
            "updated_at": now,
            "ragione_sociale":         cliente.get("ragione_sociale") or "",
            "partita_iva":             piva,
            "codice_fiscale":          cliente.get("codice_fiscale") or "",
            "indirizzo":               cliente.get("indirizzo") or "",
            "email":                   cliente.get("email") or "",
            "telefono":                cliente.get("telefono") or "",
            "pec":                     cliente.get("pec") or "",
            "codice_sdi":              cliente.get("codice_sdi") or "",
            "denominazione_struttura": cliente.get("denominazione_struttura") or "",
            "indirizzo_scarico":       cliente.get("indirizzo_scarico") or "",
            "tipologia":               cliente.get("tipologia") or "hotel",
            "listino_id":              cliente.get("listino_id"),
            "condizioni_pagamento":    cliente.get("condizioni_pagamento") or "30gg",
            "giorni_ritiro":           cliente.get("giorni_ritiro") or [],
            "note":                    cliente.get("note") or "",
            "attivo":                  True,
            "import_source":           "excel",
            "imported_at":             now,
        }
        try:
            await db.clienti.insert_one(doc)
            inserted += 1
        except Exception as e:  # pragma: no cover
            errors.append({"denominazione": denom, "error": str(e)[:200]})

    await log_audit(user, "IMPORT", "clienti", tid, {
        "inserted": inserted, "skipped": skipped, "errors": len(errors), "source": "excel",
    })
    return {
        "ok": True,
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
        "message": f"Importati {inserted} clienti · {skipped} saltati",
    }
