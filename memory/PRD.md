# CleanTec - PRD

## Original Problem
Build "CleanTec" - integrated ERP+MES+WMS+TMS for industrial laundry (clienti, ritiri/consegne, lotti, lavorazioni, tracciabilità, magazzino, fatturazione, KPI, RBAC).

## Stack
- Backend: FastAPI + Motor + MongoDB (connection pool maxPoolSize=200 for scale)
- Frontend: React 19 + Tailwind + Shadcn/UI + Phosphor Icons + Recharts
- Auth: JWT (Bearer + optional cookie)
- i18n scaffolding for multilingua (IT default)
- Object Storage: Emergent Object Storage (via EMERGENT_LLM_KEY)
- Notifications: Twilio (optional) with stub fallback for dev

## Implemented (updated 23 Apr 2026)
### Auth & RBAC
- JWT auth with bcrypt; 6 roles (admin, produzione, logistica, qualita, contabilita, cliente)
- ErrorBoundary + filtro estensioni browser

### Anagrafiche
- Clienti / Articoli / Macchine / Utenti (CRUD + RBAC)

### Operations (ciclo completo)
- Accettazione merce con ritiri + lotti multipli
- Tracciabilità 9 stati (ritirato→…→consegnato) con storico
- MES Kanban produzione (drag & drop)
- Controllo Qualità (non conformità)
- Logistica: consegne, autisti, auto-update lotti

### Amministrazione
- Fatturazione con righe/IVA/stati/scadenziario

### Dashboard & KPI
- KG oggi, lotti attivi, macchine, puntualità reale, fatturato, trend 7gg

### Interfacce dedicate
- Touch (tablet), Mobile (autisti), Portale Cliente (role=="cliente")

### Magazzino (P1 ✓)
- Detergenti/DPI, scorte minime, allarmi, movimenti

### Manutenzione (P1 ✓)
- Ticket guasti + interventi + fermo-macchina tracking

### Object Storage (P1 ✓)
- Upload foto + firme canvas digitali
- `/api/files/upload`, `/api/files/signature`, `/api/files/{path}?auth={token}`
- Wirati in Accettazione, Qualità, Consegne, Ticket Manutenzione
- **Tested end-to-end 23 Apr (iteration 8 - 100% backend)**

### Notifications SMS/WhatsApp (P1 ✓ - 23 Apr)
- Provider Twilio con fallback STUB (log-only) se mancano env
- Templates pre-built: consegna_in_transito, consegna_completata, ritiro_programmato, ticket_critico, lotto_pronto, scorta_bassa
- Auto-trigger su PATCH `/api/consegne` (stato=in_transito|consegnata) → SMS al cliente
- Auto-trigger su POST `/api/tickets` con priorità=critica → SMS a MAINTENANCE_ALERT_PHONE
- Pagina UI `/notifiche` per invio manuale + storico + KPI
- **Env opzionali per attivare Twilio:** TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, TWILIO_WHATSAPP_FROM, MAINTENANCE_ALERT_PHONE

### Hardware ingestion (P1 ✓ - 23 Apr)
- REST endpoints per bridge on-premise / daemon USB / gateway IoT
- `/api/hardware/scan` — barcode/QR → lookup lotti/articoli/consegne/ritiri
- `/api/hardware/scale` — peso lotto da bilancia USB (aggiorna peso_kg su lotto)
- `/api/hardware/rfid` e `/rfid/batch` — lettura tag singoli o gate batch
- `/api/hardware/events` — storico con filtro kind
- Pagina UI `/hardware` con 3 card operative + lista eventi

### Architettura
- Backend modulare (11 router domain-specific: auth, users, catalog, operations, billing, dashboard, magazzino, manutenzione, files, notifications, hardware)
- Pydantic schemas dedicati per PATCH
- Counter atomici per numerazioni
- MongoDB BSON datetime nativo
- Audit log completo

## Roles / Demo credentials
| Email | Password | Role |
|-------|----------|------|
| admin@cleantec.it | admin123 | admin |
| produzione@cleantec.it | produzione123 | produzione |
| logistica@cleantec.it | logistica123 | logistica |
| qualita@cleantec.it | qualita123 | qualita |
| contabilita@cleantec.it | contabilita123 | contabilita |
| cliente@cleantec.it | cliente123 | cliente (→ Hotel Excelsior Roma) |

## Backlog (P2)
- Business Intelligence: previsione carichi, analisi consumi, forecast fatturato
- Inventario biancheria a noleggio per cliente (rotazione capi)
- Multi-tenant isolation + hardening per scale (Redis cache, rate limiter)
- Firme Twilio webhook per delivery receipts (status callback)
- Short-lived signed URLs per /api/files (sostituire ?auth= con HMAC)
- TTL index su db.hardware_events (retention)

## Next Action Items
- Configurare credenziali Twilio reali (quando l'utente le fornisce)
- P2 BI reporting
