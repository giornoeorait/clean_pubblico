# CleanTec - PRD (updated 07 Lug 2026 · Email conferma ordine al cliente)

## Latest changes (08 Lug 2026)
- **Fix email conferma ordine al cliente** (`_send_order_confirmation_to_client`):
  - Ora **parsifica indirizzi multipli** separati da virgola/punto-virgola/spazio: es. `"a@x.it, b@x.it; c@x.it"` → invio a tutti e 3.
  - **Fallback su PEC**: se il campo `email` è vuoto, usa `pec` (comune per strutture italiane che hanno solo PEC).
  - Deduplica indirizzi (case-insensitive), valida presenza `@` e TLD.
  - Log persistente **sempre attivo**, incluso status `skipped` (con motivazione errore): permette diagnostica in produzione anche quando nessuna email viene trovata.
  - Nuovo campo `client_email_last_error` per il messaggio d'errore.
  - Se anche un solo destinatario riceve OK, status = "sent"; altrimenti "failed" o "logged".

## Latest changes (07 Lug 2026)
- **Email conferma ordine al cliente** (portale B2B):
  - Quando un cliente conferma un ordine dal portale pubblico, il sistema invia automaticamente una **email di conferma AL CLIENTE** all'indirizzo `email` in anagrafica (in aggiunta alla notifica interna preesistente).
  - Testo: intestazione cliente, numero ordine, data consegna richiesta, elenco articoli, totale stimato, eventuale "ritiro in lavanderia", eventuali note. Oggetto: `Conferma ordine {numero} - CleanTec`.
  - Registrazione stato: nuovi campi ordinativo `client_emails_sent[]`, `client_email_last_status`, `client_email_last_at`, `client_email_last_to`.
  - Nuovo endpoint `POST /api/ordinativi/{oid}/reinvia-conferma` per invio manuale (accessibile ad admin/logistica/contabilita).
  - UI Ordinativi: nuova icona **Envelope** nella colonna Azioni + badge stato (sent/failed/logged) sotto il numero.
  - Robusto contro cliente senza email (status='skipped', no errore).

## Latest changes (01 Lug 2026 - III · Batch 5 modifiche fatturazione)
- **MOD 1 — Fattura per Ragione Sociale**: nuovi endpoint `GET /fatture/ragioni-sociali` (elenco RS con 2+ clienti) e `GET /fatture/fatturabili-rs?ragione_sociale=…` (DDT non fatturati di tutti i clienti-fratelli). `POST /fatture` accetta `ragione_sociale_mode=true` per validare cross-cliente. UI Fatture: toggle "Cliente / Ragione Sociale" nel dialog Nuova Fattura + dropdown RS.
- **MOD 2 — Storico Apr+Mag 2026**: aggiunti a `STORICO_PREAPP_MONTHS`; nuovo endpoint `POST /fatturato-storico/aggregato` per registrare totale mensile senza dettaglio cliente. Popolati aprile 30.153,95 € + maggio 34.031,20 € (test verificato: `fatturato_anno` include ora 64.185,15 €).
- **MOD 3 — Ordinamento cronologico DDT in fattura**: `POST /fatture` ordina i DDT per (data, numero) prima di salvare `ddt_dettagli`. `GET /fatture/{fid}` ri-ordina in output. `pdf_service.generate_fattura_pdf` ordina anche al momento del rendering PDF.
- **MOD 4 — Invio email**: `smtp_service.send_email` ora supporta `attachments`. Nuovo endpoint `POST /fatture/{fid}/send-email` che genera PDF al volo, lo allega, invia via SMTP configurato e registra su fattura i campi `emails_sent[]`, `email_last_status`, `email_last_at`, `email_last_to`. UI: icona busta nella colonna azioni + dialog con pre-popolamento (email_fatturazione → email → PEC) + badge stato invio (sent/failed/logged) sotto il numero fattura.
- **MOD 5 — Doppia numerazione F/C**: helper `_iva_suffix` (iva>0 → F, iva=0 → C); `_next_fattura_seq` supporta le due serie indipendenti con riempimento buchi interni + partenza da `max globale + 1`. Nuove fatture producono es. `FT-2026-00067F` / `FT-2026-00066C`. Le fatture pregresse mantengono il format vecchio.

## Modifica 6 (riprogettazione Dipendenti) — RIMANDATA
Non ricevuta conferma per Fase A/B nel messaggio utente. Da concordare in un batch successivo.

## Latest changes (01 Lug 2026 - II)
- **Permessi granulari per-sezione** (Opzione 1: matrice sezione × view/edit):
  - Backend `core.py`: costanti `PERMISSION_SECTIONS` (14 sezioni) + `_ROLE_DEFAULT_PERMISSIONS` (default per admin/contabilita/logistica) + helper `resolve_permissions`, `has_permission`, `require_permission`.
  - Nuovo campo doc user: `permissions: {section: {view, edit}}`. Se assente/null → si applicano i default del ruolo.
  - `POST /auth/login` e `GET /auth/me` restituiscono ora `user.permissions_resolved` (matrice risolta).
  - `PATCH /api/users/{uid}` accetta e sanifica `permissions` (accetta solo chiavi sezione conosciute + coerce boolean).
- **Frontend**:
  - `lib/permissions.js`: hook `usePermissions()` espone `canView(section)` / `canEdit(section)`. Admin bypassa tutto.
  - `components/Layout.jsx`: sidebar ora filtra per `canView(section)`, coerentemente con il backend.
  - `pages/Utenti.jsx`: nuova azione "Sliders" (icona equalizzatore) che apre un **Dialog matrice permessi** con:
    - Preset rapidi: "Solo lettura", "Tutto attivo", "Logistica standard", "Contabilità standard".
    - Checkbox per ogni sezione × (Vede / Modifica).
    - Logica di coerenza: disattivare *Vede* disattiva anche *Modifica*; attivare *Modifica* forza *Vede*.

## Latest changes (01 Lug 2026 - I)
- **Auto-riempimento buchi nella numerazione fatture** (opzione A):
  - `billing.py::_next_fattura_seq` cerca il primo buco nella sequenza `FT-YYYY-NNNNN` del tenant/anno corrente e riutilizza quel numero prima di incrementare il counter globale.
  - Riallineamento automatico del counter globale se dietro rispetto al max effettivo del DB (safe dopo restore).
- **Rinumerazione manuale fattura** (opzione B):
  - Nuovo endpoint `PATCH /api/fatture/{fid}/rinumera` (body: `seq` o `numero` completo).
  - Validazioni: formato `FT-YYYY-NNNNN`, anno coerente con `fattura.data.year`, univocità per tenant/anno.
  - Blocco fiscale: rifiuta 409 se `xml_transmitted=true`.
  - Aggiorna denormalizzazione: DDT collegati vedono il nuovo `fattura_numero`.
- **Flag "trasmessa a SDI"** per proteggere l'immutabilità fiscale:
  - Nuovi campi doc fattura: `xml_transmitted`, `xml_transmitted_at`, `xml_transmitted_by`.
  - Endpoint `POST /api/fatture/{fid}/segna-trasmessa` (blocca il numero).
  - Endpoint `POST /api/fatture/{fid}/annulla-trasmissione` (SOLO admin, per errori).
  - Sull'eliminazione: bottone Trash nascosto se `xml_transmitted=true` (impedisce eliminazione di fatture ufficialmente inviate).
- **UI Fatture.jsx**:
  - Nuova icona **matita** (`fatt-renum-{id}`) per aprire il dialog "Rinumera fattura" con warning fiscale.
  - Nuova icona **aeroplanino** (`fatt-segna-sdi-{id}` / `fatt-sblocca-sdi-{id}`) per toggle SDI-trasmesso.
  - Badge **SDI** sotto il numero fattura quando trasmessa.

## Latest changes (30 Giu 2026)
- **Punto 1 — Riepilogo cumulativo articoli in fattura**:
  - `billing.py create_fattura` calcola e salva `ddt_dettagli` (lista DDT inclusi con numero/data/imponibile/righe_count) + `riepilogo_articoli` (aggregato per articolo: qty_totale, prezzo_unitario_medio ponderato, totale).
  - `GET /api/fatture/{fid}` esegue backfill on-the-fly per fatture vecchie.
  - `pdf_service.generate_fattura_pdf` ora include due nuove tabelle: "D.D.T. inclusi in fattura" e "Riepilogo cumulativo articoli".
  - UI `Fatture.jsx` mostra entrambe le sezioni nel dialog di dettaglio (testid `fatt-detail-ddt`, `fatt-detail-riepilogo`).
- **Punto 2 — Recap cumulativo ordinativi**:
  - Nuovo endpoint `GET /api/ordinativi/recap` (registrato prima di `/{oid}` per evitare conflict). Esclude `convertito_ddt` e `annullato`. Ritorna items aggregati (qty, conteggi per stato, prima data) + totali.
  - UI `Ordinativi.jsx` pannello "Carico produzione residuo" (testid `ord-recap-panel`) sotto la tabella, con griglia e BarChart Recharts orizzontale.
  - Quando un ordinativo viene convertito in DDT lo stato passa a `convertito_ddt` → automaticamente escluso dal recap.
- **Punto 3 — Flag operativi DDT**:
  - Nuovo endpoint `PATCH /api/ddt/{id}/operativi` con campi `consegnato` e/o `ritirato_sporco`. Salva timestamp + nome utente. Funziona anche su DDT fatturati senza alterare dati fiscali.
  - UI `DDT.jsx` colonna "Operativi" con due bottoni toggle (testid `ddt-flag-consegnato-{id}` / `ddt-flag-sporco-{id}`) + tooltip con data/ora/utente.
- **Punto 4 — Dashboard KPI "Da fatturare mese corrente"**:
  - Nuovi campi in `/api/dashboard/kpi`: `fatturare_mese_importo`, `fatturare_mese_count`, `fatturare_mese_serie_cumul` (serie giornaliera cumulativa).
  - UI Dashboard: KPI dedicato + LineChart cumulato giornaliero.
- **Punto 5 — Integrazione storico pre-app Gen/Feb/Mar 2026**:
  - Costante `STORICO_PREAPP_MONTHS = [(2026,1),(2026,2),(2026,3)]` in `dashboard.py`.
  - `/api/dashboard/kpi` nuovi campi: `fatturato_anno`, `fatturato_anno_fatture`, `fatturato_anno_storico`, `storico_totale_anno`, `storico_mesi_inclusi`, `anno_corrente`. De-duplicazione: se per un mese esistono già fatture vere, lo storico di quel mese NON viene sommato (no doppi conteggi).
  - UI Dashboard: KPI "Fatturato 2026" con badge "incl. storico" + card descrittiva mesi inclusi.
- **Bug critico fixato in-flight dal testing agent**: TypeError datetime tz mismatch nel cumul cycle di dashboard.py (helper `_as_aware` aggiunto).
- **Iter 31 testing**: 12/12 pytest backend PASS + UI verificata (Dashboard, Ordinativi recap, DDT toggle, Fattura detail).

## Latest changes (17 Giu 2026)
- **Permesso modifica data DDT per-utente** (`can_edit_dates`):
  - Backend: aggiunto campo `can_edit_dates: bool` su modello User (`schemas.py` UserCreate + PatchUserIn). Salvato in DB e ritornato da `/auth/me`.
  - Backend: `ddt.py` PATCH ora controlla `role == 'admin' OR can_edit_dates`. Messaggio 403 aggiornato: "Non hai i permessi per modificare la data del DDT".
  - Frontend: `permissions.js` → `canEditDate = isAdmin || user?.can_edit_dates`.
  - Frontend: pagina `/utenti` ha nuova colonna **Permessi** con badge toggle ("Modifica data DDT" / "No modifica date"). Admin è readonly (sempre ON).
  - Form Nuovo Utente: checkbox dedicato `Può modificare la data dei DDT`.
- **Modifica data Ordinativi rimossa** (l'utente vuole solo DDT). Editor `data_richiesta` rimosso da `Ordinativi.jsx` e dal backend (`OrdinativoPatch` non contiene più il campo).
- **ClienteCombobox con ricerca** (`components/ClienteCombobox.jsx`):
  - Popover + Command/cmdk
  - Ordinamento alfabetico (denominazione_struttura / ragione_sociale)
  - Campo di ricerca con match substring case-insensitive
  - Prop `allowAll` per filtri (es. "Tutti i clienti")
  - Prop `showListinoBadge` per indicare cliente con/senza listino
  - Sostituisce il vecchio Select cliente in **DDT.jsx (form + filtro)** e **Ordinativi.jsx (form)**.
- **Iter 30 testing**: 9/9 pytest backend PASS + UI verificata.

## Latest changes (15 Giu 2026)
- **RBAC date editing**: solo gli admin possono modificare la data dei DDT e degli ordinativi (campo data_richiesta). Backend rifiuta con 403 se non admin (`ddt.py` linee 197-200, `ordinativi.py` linee 268-276).
- **Frontend gating prezzi** (`lib/permissions.js` + `useCanSeePrices`/`canEditDate`):
  - Dashboard: KPI Fatturato/Sospesi/Incassato nascosti per logistica
  - DDT: colonna Imponibile + totale aggregato nascosti per logistica
  - Ordinativi: colonna Totale + preview prezzi + footer totale nascosti per logistica
- **Colonna "Pezzi"** (somma quantità riga) in tabelle DDT e Ordinativi (sostituisce conteggio righe).
- **Ordinamento alfabetico clienti** (per denominazione_struttura / ragione_sociale) nei Select di DDT e Ordinativi.
- **Soglia 50€ portale B2B** (`PortalePublic.jsx`): ordine con totale < 50€ apre dialog 'Ordine sotto soglia minima' con bottoni 'Modifica ordine' / 'Conferma con ritiro lavanderia'. Quest'ultimo salva `ritiro_lavanderia: true` sull'ordinativo. Backend `PortaleOrdIn` accetta nuovo campo opzionale.
- **Badge "Ritiro lavanderia"** mostrato in tabella Ordinativi accanto al numero.
- **Iter 29 testing**: 11/11 pytest passati + UI verificata via screenshot per admin e logistica.

## Latest changes (14 May 2026)
- Fix JSX syntax in `Clienti.jsx` and `DDT.jsx` (mismatched div/trailing `v>`)
- Swap label priority globally: **Denominazione struttura** primary, **Ragione sociale** secondary
- UI validato con screenshot tool su /clienti, /ddt e dashboard — nessun crash, etichette corrette


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
- **11 May 2026 (pomeriggio) — INVIO LINK PORTALE VIA EMAIL**
  - Backend: nuovo endpoint `POST /api/clienti/{cid}/invia-link-portale` body `{tipo: self_service|diretto, to_override?, base_url?}` → invia email al cliente (campo email dell'anagrafica, con override opzionale) con il link al portale
    - **tipo=self_service**: link generico `/portale` dove il cliente si identifica via P.IVA/CF
    - **tipo=diretto**: link personalizzato `/ordina/{token}` (genera token statico al volo se mancante)
    - Costruzione URL completo: priorità a `base_url` passato dal frontend (origin del browser), fallback a `company.sito`
  - Backend: usa `smtp_service.send_email` esistente con body sia text che HTML stylato; se SMTP non configurato, fa fallback stub (logga in `email_events`) e ritorna status nel response
  - Backend: audit log `EMAIL_SEND` con context (cliente_id, tipo, to, status)
  - Frontend: due nuovi bottoni "Email" nel pannello "Portale cliente" del profilo, uno per ciascun tipo di link. Disabilitati se email cliente mancante. Confirm dialog prima dell'invio; toast differenziato per "sent" / "logged (SMTP not configured)" / "failed"
  - Frontend: il bottone "Genera & invia" sostituisce "Genera link diretto" quando il cliente ha email — genera token + invia in un'unica azione
  - **Verificato E2E**: invio self-service → status=logged (stub) perché SMTP demo non configurato; invio diretto → genera token + invio. UI mostra entrambi i bottoni Email correttamente.

- **11 May 2026 — PORTALE SELF-SERVICE (P.IVA/CF lookup)**
  - Backend: nuovo endpoint pubblico `POST /api/public/portale/lookup` body `{identificativo}` → cerca cliente cross-tenant su `partita_iva` OR `codice_fiscale` (esatto, case-insensitive), genera session token effimero TTL 1h salvato in `portale_sessions`
  - Backend: helper `_resolve_portale_token` unifica risoluzione token statico (`clienti.portale_token`) e sessione effimera — riusa l'intero flusso esistente (GET catalogo + POST ordinativo)
  - Backend: **anti-enumeration** stesso 404 per non-trovato e disattivato; **rate-limit 10 fail/60s** per identificativo (collezione `portale_lookup_failed`); fix timezone mismatch Mongo (naive) vs `now_utc()` (aware)
  - Backend: **TTL indexes** creati allo startup su `portale_sessions.expires_at` (0s) e `portale_lookup_failed.at` (300s) per cleanup automatico
  - Frontend: nuova pagina pubblica `/portale` con form input P.IVA/CF, card di conferma con ragione sociale e indirizzo, bottoni "Non sono io" / "Continua" → redirect a `/ordina/{token}` esistente
  - Frontend: pannello "Portale cliente" in profilo Clienti ora espone DUE link (self-service `/portale` + token statico opzionale `/ordina/{token}`)
  - Frontend: AuthContext skippa `/auth/me` anche su `/portale` (no 401 in console)
  - **Iter 23: 12/12 backend + frontend E2E ✅** + verifica manuale rate-limit (429 dopo 10 fail) e screenshot UI Hotel Excelsior Roma identificato correttamente

- **24 Apr 2026 (pomeriggio post-5) — BATCH P3 "Anagrafiche HR + Alerts + Export PDF + Quality"**
  - Backend: `/api/dipendenti` CRUD (nome, ruolo, codice_fiscale, email, tipo_contratto, stipendio_mensile, ore_contrattuali, data_assunzione, attivo)
  - Backend: `POST /api/dipendenti/genera-stipendi {mese_riferimento}` — crea voci costo categoria=personale per ogni dipendente attivo con stipendio>0. Idempotente (skip duplicati su stesso mese+nome+tipo_rapporto=stipendio)
  - Backend: `/api/automezzi` CRUD con targa univoca per tenant (409 su duplicato)
  - Backend: `GET /api/alerts` aggregatore con 4 tipi: `costo_soglia` (spesa >120% media 3m), `fattura_scaduta` (data_scadenza<oggi), `fattura_scadenza` (<=3gg), `aging_sospeso` (>60gg). Ordinati per severity
  - Backend: `GET /api/reports/{tipo}/pdf?anno=` per tutti i 6 report BI — generazione via ReportLab con header azienda, KPI strip, tabelle styled indaco
  - Backend: validator regex `^\d{4}-(0[1-9]|1[0-2])$` su `Costo.mese_riferimento` (422 su formati invalidi)
  - Frontend: nuova pagina `/dipendenti` con toggle attivo + dialog "Genera stipendi"
  - Frontend: nuova pagina `/automezzi` con targa auto-uppercase
  - Frontend: `AlertsBanner` componente integrato in Layout, fetch ogni 5 min, dismissable, click alert → navigazione contestuale
  - Frontend: Costi con dropdown intelligenti (dipendenti attivi + targhe automezzi) con fallback "— libero —"
  - Frontend: bottone "Scarica PDF" in ogni tab Report
  - Frontend: ErrorBoundary con supporto `resetKeys` (auto-reset al cambio tab/anno) + ErrorBoundary locale in Report.jsx
  - Frontend: `DialogDescription` aggiunta ai nuovi dialog per pulizia warning Radix a11y
  - Sidebar: nuove voci Dipendenti + Automezzi (icone Users/Truck) sotto Costi
  - **Iter 22: 40/40 backend + 100% frontend ✅**

- **24 Apr 2026 (tarda notte+) — FASE 5 "Report & Statistiche BI"**
  - Backend: nuovo router `/api/reports` read-only con 6 endpoint aggregati:
    - `GET /fatturato?anno=` → totale, incassato, sospeso, per_mese (grouped BSON date → %Y-%m), top 20 per_cliente
    - `GET /produzione?anno=` → totale_kg (qta × peso_medio), totale_pezzi, per_mese, top 20 per_cliente, top 20 per_articolo
    - `GET /costo-kg?anno=` → totale_costi, totale_kg, costo_kg_medio €/kg, per_categoria, per_mese con costo_kg mensile
    - `GET /aging-sospesi` → 4 bucket (0-30, 31-60, 61-90, >90 gg dalla data fattura), totale_sospeso, dettagli top 50
    - `GET /km-automezzi?anno=` → totale_km, totale_spesa, per_targa (km/spesa/costo_km/per_tipo breakdown), per_mese
    - `GET /marginalita?anno=` → fatturato − costo allocato per kg, per_cliente ordinato per margine DESC
  - Backend: aggregazioni Mongo pipeline pulite, BSON datetime supportato per fatture/ddt, string yyyy-mm per costi
  - Frontend: nuova pagina `/report` con 6 tab + Recharts (BarChart/LineChart/PieChart), selettore anno
  - Frontend fix CRITICO post-iter20: race condition su cambio tab risolta con `setData(null)` sincrono in onClick + defensive `(arr||[]).map` su tutte le shape eterogenee
  - **Iter 19-21: 23/23 backend + 100% frontend (6/6 tab)  ✅**

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
- 🎉 **Tutte le fasi P0/P1/P2/P3 completate** (1, 2a, 2b, 3a, 3b, 4, 5, P3 HR+Alerts+PDF export+Quality)
- ✅ **Backup Automatici Cloud** (13 Mag 2026) — snapshot giornalieri 03:00 UTC su Emergent Object Storage, retention 7, manuale + auto, restore merge/replace, multi-tenant isolation. Iter 24: 12/12 backend + 100% frontend ✅
- (P2 / Future) Generazione XML FatturaPA (B2B/PA elettronica)
- (P4 / Future) Migrazione Report a react-query/SWR per cache automatica invece di useState locale
- (P4 / Future) Export Excel (openpyxl) dei report oltre al PDF
- (P4 / Future) Cron/scheduled task per invio email notifica alert critici (richiede integrazione Resend/SendGrid)
- (P4 / Future) Dashboard widget "Alert attivi" con contatore badge in sidebar
- (P4 / Future) Allegare PDF report al profilo cliente/fornitore per archiviazione storica
- (P4 / Future) Esporre `delete_object` in storage.py per pulire snapshot orfani su delete
- Configurare Stripe LIVE key in produzione
