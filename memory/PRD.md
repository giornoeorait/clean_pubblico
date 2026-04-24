# CleanTec - PRD (updated 24 Apr 2026 · FASE 4 Costi)

## Problem
Industrial laundry **commercial SaaS** — ERP focalizzato sul flusso commerciale: Clienti → Articoli → Listini → Offerte → D.D.T. → Fatture → Sospesi. Ciclo acquisti: Fornitori → DDT ricevuti → Fatture passive. Portale cliente pubblico per ordinativi self-service.

## Stack
- Backend: FastAPI + Motor + MongoDB
- Frontend: React 19 + Tailwind + Shadcn/UI + Phosphor Icons + Recharts
- Auth: JWT con tenant_id nei claims
- Storage: Emergent Object Storage
- Pagamenti: Stripe via emergentintegrations

## Architecture (post-refactor 24 Apr 2026)

### Flusso dati
```
Articoli ──┐
           ├──► Listini (prezzi per articolo)
Clienti ◄──┘        │
   │                ▼
   └──► D.D.T. (auto-prezza da listino cliente)
             │
             ▼
       Fatture (aggregazione DDT non fatturati)
             │
             ▼
       Sospesi (incasso / mark incassata)
```

### Collezioni DB
- `tenants` — multi-tenant SaaS
- `users` — {id, email, role, tenant_id}
- `clienti` — {id, tenant_id, ragione_sociale, listino_id, ...}
- `articoli` — {id, tenant_id, codice, descrizione, prezzo, ...}
- `listini` — {id, tenant_id, nome, attivo}
- `listini_prezzi` — {tenant_id, listino_id, articolo_id, prezzo}
- `ddt` — {id, tenant_id, numero, cliente_id, listino_id, righe[], imponibile, stato_fatturazione, fattura_id}
- `fatture` — {id, tenant_id, numero, cliente_id, ddt_ids[], totale, stato_incasso, data_incasso}
- `payment_transactions` — Stripe history

### Backend routers (attivi)
auth, users, catalog (clienti+articoli), listini, ddt, billing (+sospesi), dashboard, files, tenants, subscriptions, superadmin

### Frontend pagine (attive)
Login, Register, Pricing, VerifyEmail, Dashboard, Clienti, Articoli, Listini, DDT, Fatture, Sospesi, Utenti, Billing, SuperAdmin

## Piani SaaS (aggiornati)
| Piano | Mensile | Annuale | Utenti | DDT/mese | SMS |
|-------|---------|---------|--------|---------|-----|
| Starter | €59 | €49 | 5 | 500 | 0 |
| Pro | €179 | €149 | 20 | 5.000 | 100 |
| Enterprise | €449 | €379 | ∞ | ∞ | 500 |

## Demo credentials
| Email | Password | Role |
|-------|----------|------|
| super@cleantec.it | Superadmin123! | superadmin |
| admin@cleantec.it | admin123 | admin |
| logistica@cleantec.it | logistica123 | logistica |
| contabilita@cleantec.it | contabilita123 | contabilita |

## Changelog recente
- **24 Apr 2026 (tarda notte) — FASE 4 "Costi"**
  - Backend: nuovo router `/api/costi` con CRUD + `GET /api/costi/summary?anno=YYYY` (aggregazioni Mongo: per_categoria, per_mese, stack mese×categoria, totale_generale)
  - Backend: 4 categorie validate (`personale`, `automezzi`, `utenze`, `prodotti`); campi comuni (data, mese_riferimento yyyy-mm, descrizione, importo≥0) + campi OPZIONALI context-aware (dipendente/ore, targa/km/tipo costo, tipo utenza/consumo/unità, codice articolo/qtà); fornitore_id opzionale (verifica esistenza → 400)
  - Backend: filtri list `categoria`, `mese_riferimento`, `anno`, `fornitore_id`; RBAC admin+contabilita su write, lettura a tutti
  - Backend schemas: `CostoIn`, `PatchCostoIn` aggiunti in coda a `schemas.py`
  - Frontend: nuova pagina `/costi` con layout unificato:
    - 4 KPI cards categoria (cliccabili per cambio tab) con totali annuali
    - Strip con Totale generale + selettore anno + selettore mese (filtra lista + summary)
    - Bar chart mensile semplice (12 barre, altezza ∝ totale mese)
    - 4 tab categoria con tabelle colonne-specifiche (dipendente per personale, targa+km per auto, ecc.)
    - Dialog dinamico: categoria pre-selezionata dal tab attivo (fix post-test iter18)
  - Frontend: voce sidebar "Costi" (icon Wallet) tra Fatture fornitore e Utenti
  - **Iter 18: 22/22 backend + 100% frontend ✅** (un bug UX MEDIUM trovato e fixato: dialog "Nuovo costo" ora apre con categoria allineata al tab)

- **24 Apr 2026 (notte+) — FASE 2b "Fornitori + ciclo passivo"**
  - Backend: nuovo router `/api/fornitori` con CRUD + filtri `q`/`categoria` + `GET /{fid}/profilo` (ddts, fatture, stats: spesa_totale, pagato, da_pagare). Delete 409 se ha documenti collegati
  - Backend: `/api/ddt-fornitore` CRUD con numero interno `FORN-DDT-YYYY-NNNNN`, `fornitore_snapshot` immutabile, `stato_fatturazione` = non_fatturato|fatturato, PATCH/DELETE 409 se fatturato
  - Backend: `/api/fatture-fornitore` CRUD con numero `FORN-FT-YYYY-NNNNN`, 2 modalità (da `ddt_fornitore_ids` oppure `righe` inline per utenze/servizi), IVA% configurabile default 22%, `PATCH /paga` imposta stato_pagamento=pagata, DELETE riapre i DDT collegati; `GET /ddt-fatturabili/{fornitore_id}`; PATCH iva_perc ricalcola anche fatture legate a DDT
  - Backend: counters separati `ddt_fornitore`/`fattura_fornitore` (non confondibili col ciclo vendite)
  - Backend: RBAC — admin=tutto; contabilita=CRUD fornitore e fatture (no delete fornitore); logistica=solo DDT (create/edit)
  - Backend schemas: `FornitoreIn`, `PatchFornitoreIn`, `DdtFornitoreIn`, `FatturaFornitoreIn`, `RigaDocFornIn` aggiunti in `schemas.py`
  - Frontend: 3 pagine nuove — `/fornitori` (anagrafica con profilo 4 KPI cards + tabelle), `/fornitori/ddt` (lista+dialog righe editable, stato→fattura linkata), `/fornitori/fatture` (toggle "Da DDT" / "Righe manuali", preview live Imponibile+IVA+Totale, azione Paga)
  - Frontend: sidebar aggiunte 3 voci (Fornitori, DDT ricevuti, Fatture fornitore) con icone Factory/Truck/Receipt
  - Frontend fix cosmetico: `AuthContext` skippa `/auth/me` ping su route `/ordina/*` → console pulita su portale pubblico (era 401 pre-esistente da iter16)
  - **Iter 17: 21/21 backend + 100% frontend ✅**

- **24 Apr 2026 (notte) — FASE 3b "Ordinativi + Portale cliente pubblico"**
  - Backend: nuovo router `/api/ordinativi` CRUD + `POST /{id}/converti-ddt` (crea DDT-YYYY-NNNNN, marca ordinativo convertito_ddt); numerazione `ORD-YYYY-NNNNN` dedicata
  - Backend: endpoint admin `POST/DELETE /api/clienti/{cid}/portale-token` (token URL-safe 32 char via `secrets.token_urlsafe`)
  - Backend: public router (NO AUTH) `GET /api/public/portale/{token}` (ritorna cliente + articoli prezzati dal listino + fornitore) e `POST /api/public/portale/{token}/ordinativo`
  - Frontend: pagina `/ordinativi` admin con badge origine (interno/portale), converti-DDT button
  - Frontend: pagina pubblica `/ordina/{token}` — catalogo self-service con cart editable, submit ordinativo senza login
  - Frontend: pannello "Portale cliente" nel profilo Clienti (bottone occhio) con Genera/Rigenera/Revoca/Copia link
  - **Iter 16: 21/21 backend + 100% frontend ✅**

- **24 Apr 2026 (night) — FASE 3a "Offerte & Preventivi"**
  - Backend: nuovo router `/api/offerte` con CRUD completo + `POST /{id}/converti-contratto` (assegna progressivo `CT-YYYY-NNNNN` separato) + `GET /{id}/pdf?tipo=offerta|contratto`
  - Backend: schema con `righe[]` con `sconto_perc + sconto_eur` per riga; calcolo `prezzo_finale = max(0, prezzo * (1-perc/100) - eur)`; ricalcolo automatico da listino del cliente (usa `prezzo_noleggio`/`prezzo_lavaggio` in base al tipo listino)
  - Backend: stati `bozza → inviata → accettata/rifiutata → contratto`; offerta in stato `contratto` è read-only (edit/delete → 409)
  - Backend: nuova collezione `db.termini_templates` per clausole riusabili (GET admin+contabilita, POST/DELETE solo admin) + 4 clausole default seed (pagamento, durata, responsabilità, foro)
  - Backend: `pdf_service.generate_offerta_pdf(as_contratto=True|False)` — PDF contratto differenziato con titolo "CONTRATTO DI SERVIZIO N.", data di attivazione, signature boxes finali
  - Backend: counters `offerta` e `contratto` distinti, tenant-scoped migrato
  - Frontend: nuova pagina `/offerte` (admin+contabilita) con tabella stati colorati, dialog form con: select cliente + durata mesi + scadenza + righe editable con preview live sconto (line-through + totale) + termini da template o manuali
  - Frontend: sidebar "Offerte & Preventivi" tra Listini e D.D.T., icon HandHeart
  - Frontend: azioni contestuali per stato: Invia → Accetta/Rifiuta → Trasforma in contratto; doppio PDF (offerta + contratto) + Duplica
  - **Iter 15: 19/19 backend + 100% frontend ✅**

- **24 Apr 2026 (evening+) — FASE 2a "Anagrafiche potenziate"**
  - Backend schema: `ClienteIn` con 5 campi obbligatori (ragione_sociale, partita_iva, indirizzo, email EmailStr, telefono) + 4 opzionali (pec, codice_sdi, denominazione_struttura, indirizzo_scarico); `sla_ore` rimosso
  - Backend schema: `ArticoloIn` con nuovi driver `prezzo_noleggio`, `prezzo_lavaggio`, `giacenza`; label UI "Valore convenzionale singolo prodotto (IVA esclusa)" per il campo `prezzo`
  - Backend: `ListinoIn.tipo` obbligatorio al create (pattern `^(noleggio|lavaggio)$`); `ListinoPatch` non include `tipo` (immutabile dopo creazione)
  - Backend: `GET /api/listini/{id}/prezzi` ora ritorna `{listino:{id,nome,tipo,attivo}, rows:[...]}` — `prezzo_default` viene da `prezzo_noleggio` o `prezzo_lavaggio` in base al tipo del listino
  - Backend: nuovo endpoint `GET /api/clienti/{id}/profilo` → cliente + listino + ddts + fatture + stats (ddt_totali, fatturato_totale, incassato_totale, sospeso_totale)
  - Backend: `seed.migrate_phase2` one-shot — listini preesistenti → tipo=lavaggio; articoli → prezzo_noleggio=prezzo*0.1 + prezzo_lavaggio=prezzo*0.07 + giacenza=0; clienti → unset sla_ore
  - Frontend Clienti: form diviso in 2 sezioni visivamente distinte (Ragione sociale / Denominazione struttura), * rossi su required, banner warning se mancano, bottone occhio → dialog profilo con 4 KPI cards + tabella fatture/DDT con PDF inline
  - Frontend Articoli: grid 2×2 card con Noleggio, Lavaggio, Giacenza, V. convenzionale
  - Frontend Listini: scelta tipo come 2 bottoni binari al create, badge tipo visibile nella lista, tipo read-only in edit
  - **Iter 14: 11/11 backend + 100% frontend + regressione verde ✅**

- **24 Apr 2026 (evening) — FASE 1 "Fondamenta" completata**
  - Backend: nuovo router `/api/company` per anagrafica azienda madre (CRUD + upload logo WebP, max 4 MB, resize 512×512) — per-tenant singleton, RBAC admin-only
  - Backend: `pdf_service.py` con ReportLab → `generate_ddt_pdf` e `generate_fattura_pdf` con intestazione azienda (sx + logo) + cliente (dx), footer "Fattura di cortesia"
  - Backend: nuovi endpoint `GET /api/ddt/{id}/pdf` e `GET /api/fatture/{id}/pdf` (Content-Type application/pdf)
  - Backend: `PATCH /api/ddt/{id}` già esistente, ora usato anche da UI per editare DDT non fatturati (blocca edit se `stato_fatturazione=fatturato`)
  - Frontend: nuova pagina `/azienda` con form completo (10 campi, * sui required), upload logo con preview e delete
  - Frontend: setup wizard first-run — Layout rileva admin con `setup_complete=false` e reindirizza automaticamente a `/azienda?first=1` con banner benvenuto
  - Frontend: bottoni "PDF" + "Modifica" sulle righe DDT, bottone "PDF" sulle righe Fatture; apertura PDF via blob URL in nuova tab
  - Frontend: voce sidebar "Anagrafica azienda" (admin-only)
  - **Iter 13: 11/11 backend + 100% frontend ✅**

- **24 Apr 2026 (pm++) — FEATURE "Brand Scale indipendenti logo ↔ testi"**
  - Split del campo unico `brand_scale` in due campi indipendenti:
    - `logo_scale` (range 0.8 – 3.0) → dimensione logo box in sidebar + hero login
    - `text_scale` (range 0.8 – 2.5) → dimensione nome applicazione + tagline
  - Migration one-shot in `_get_or_init`: documenti con `brand_scale` legacy → backfill su entrambi i nuovi campi e `$unset` del vecchio. Testata: 1.4 → logo=1.4, text=1.4, brand_scale rimosso
  - CSS vars `--logo-scale` e `--text-scale` sulla root, applicate separatamente nei layout
  - UI Branding: nuovo componente riusabile `ScaleControl` con preset S/M/L/XL + slider granulare per ciascun controllo

- **24 Apr 2026 (pm+) — FEATURE "Brand Scale"**
  - Aggiunto selettore dimensioni (S/M/L/XL + slider fine 0.8× - 2.5×) accanto all'uploader Logo in `/admin/branding`
  - Campo `brand_scale` (0.8-2.5) persistito in `db.branding`, validato backend via Pydantic Field(ge=0.8, le=2.5)
  - CSS var `--brand-scale` globale → applicata a logo box + app_name + tagline in sidebar e pagina login tramite `calc(Npx * var(--brand-scale))`
  - Live-preview istantanea (senza reload) via CSS var hotswap durante il drag dello slider

- **24 Apr 2026 (pm) — FEATURE "Branding & estetica" (superadmin-only)**
  - Nuovo router `/api/branding` (public read) + `/api/admin/branding/*` (superadmin write/upload/delete)
  - Singleton doc `db.branding` con config globale: app_name, tagline, login_eyebrow/title/subtitle/footer, login_features[], primary/accent/dark color, paths logo/hero/favicon
  - Upload immagini via Pillow: resize + conversione WebP (hero 1920×1200, logo 512×512) / PNG (favicon 96×96), max 8MB, auto-riduzione 80%+
  - Frontend: `BrandingContext` fetcha `/api/branding`, applica `<title>` + favicon + CSS vars `--indaco/--celeste/--azzurro/--indaco-dark` (hotswap senza reload, grazie a Tailwind config che ora usa `var(--...)`)
  - Pagina `/admin/branding` (superadmin-only): form con identità / upload immagini / editor testi+features / color pickers + live preview
  - Login.jsx e Layout.jsx ora leggono il branding (logo, hero, testi, colori)
  - **Bug fix RBAC critico**: `core.require_roles('superadmin')` ora rigetta esplicitamente `admin` (prima veniva implicitly whitelisted per tutti gli endpoint `require_roles`); stessa logica applicata a `ProtectedRoute` + `Layout` sidebar filter. Questo fix chiude anche un RBAC leak preesistente su `/api/admin/stats|tenants|transactions` dove admin normale prima poteva accedere.
  - Iter 12: 18/18 backend + 6/6 frontend ✅

- **24 Apr 2026 — MAJOR REFACTOR "Pure commercial SaaS"**
  - RIMOSSE pagine: Accettazione, Logistica, Macchine, Magazzino, Manutenzione, Mobile, Notifiche, Portale, Touch, Hardware, Insights
  - RIMOSSI router backend: operations, hardware, manutenzione, magazzino, notifications, insights
  - Aggiornato `core.PLANS` con limite `ddt_monthly` (era `lotti_monthly`)
  - Pulito `seed.py`: via macchine/lotti/magazzino/tickets; focus su Clienti, Articoli, Listini (Std+VIP), 6 DDT demo
  - Semplificato Dashboard KPI: DDT, fatturato, sospesi, incassato
  - Aggiornato Pricing, Billing, Login, Utenti coerenti col nuovo flusso
  - One-shot migration in `ensure_demo_tenant`: rinomina `limits.lotti_monthly`→`ddt_monthly`, `usage.lotti_this_month`→`ddt_this_month` sui tenant esistenti
  - Numerazione fatture: prefisso `FT-YYYY-NNNNN` (confermato in `billing.py`)
  - **Testing iteration 10: 21/21 backend ✅ + 100% frontend E2E ✅** (Playwright + pytest, flusso Clienti→Listini→DDT→Fatture→Sospesi + multi-tenant isolation + 14 legacy route redirects)

- **23 Apr 2026** — Listini/DDT/Sospesi/Fatture aggregate implementati
- **Multi-tenant SaaS** — Stripe, trial, quota enforcement, email verification stub
- **Superadmin dashboard** — MRR/ARR, conversion, tenants/transactions

## Backlog (P2 / Future)
- 2FA OTP per account admin
- Stripe Customer Portal (download fatture)
- Fatturazione elettronica italiana SDI XML
- Export Excel fatture & sospesi
- Solleciti automatici via email/SMS per sospesi (Resend/Twilio)
- Report BI: fatturato per cliente, top articoli, aging sospesi

## Next Action Items
- (P2) **FASE 5 — Report & Statistiche BI**: fatturato globale/per cliente, kg/quintali prodotti (pezzi × peso), costi personale, costo produzione/kg, consegne mensili, km automezzi — ora che i Costi sono in DB, si può calcolare la marginalità reale
- (P2) Ricalcolo iva/totale UX: oggi corretto solo via PATCH iva_perc — frontend esporre editor dedicato per fatture DDT-linked
- (P3) Clausole: `Pydantic validator` su FatturaFornitoreIn "at least one of righe/ddt_fornitore_ids"; validator regex su Costo.mese_riferimento (yyyy-mm); `aria-describedby` sui DialogContent Radix
- (P3) Costi: aggiungere anagrafica dipendenti e anagrafica automezzi dedicate (ora sono campi liberi) + stipendio ricorrente mensile auto-generato
- Configurare Stripe LIVE key in produzione
