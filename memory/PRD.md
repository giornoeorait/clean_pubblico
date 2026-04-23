# CleanTec - PRD

## Original Problem
Build "CleanTec" - integrated ERP+MES+WMS+TMS for industrial laundry (clienti, ritiri/consegne, lotti, lavorazioni, tracciabilità, magazzino, fatturazione, KPI, RBAC).

## Stack
- Backend: FastAPI + Motor + MongoDB (connection pool maxPoolSize=200 for scale)
- Frontend: React 19 + Tailwind + Shadcn/UI + Phosphor Icons + Recharts
- Auth: JWT (Bearer + optional cookie)
- i18n scaffolding for multilingua (IT default)

## Implemented (23 Apr 2026)
- JWT auth with bcrypt; 5 roles (admin, produzione, logistica, qualita, contabilita)
- Anagrafiche: Clienti / Articoli / Macchine (CRUD + RBAC)
- Accettazione merce con creazione ritiro + lotti multipli
- Tracciabilità lotti (9 stati: ritirato→ricevuto→smistato→lavato→asciugato→stirato→confezionato→pronto→consegnato) con storico completo
- MES Kanban produzione (drag & drop)
- Controllo Qualità (non conformità con gravità/stato)
- Logistica: pianificazione consegne, assegnazione autisti, auto-update lotti a "consegnato"
- Fatturazione: righe, IVA, stati (bozza/emessa/pagata/scaduta), scadenziario
- Dashboard KPI: kg_oggi, lotti_attivi, macchine, puntualità, fatturato, trend 7gg, distribuzione stati
- Interfacce dedicate: Touch (produzione), Mobile (autisti), Portale Cliente
- Audit log completo
- ErrorBoundary + filtro estensioni browser (MetaMask ecc.)
- Seed demo: 5 clienti, 6 articoli, 7 macchine, 30 lotti

## Roles
| Email | Password | Role |
|-------|----------|------|
| admin@cleantec.it | admin123 | admin |
| produzione@cleantec.it | produzione123 | produzione |
| logistica@cleantec.it | logistica123 | logistica |
| qualita@cleantec.it | qualita123 | qualita |
| contabilita@cleantec.it | contabilita123 | contabilita |

## Backlog (P1)
- Magazzino detergenti/DPI con scorte minime e lotti/scadenze
- Manutenzione macchine (piani, ticket guasti, fermo macchina)
- Integrazioni bilance/RFID/barcode hardware
- Notifiche SMS/WhatsApp
- Firme digitali e upload foto (S3/object storage)
- Inventario biancheria a noleggio per cliente
- Business intelligence: previsione carichi, analisi consumi
- Multi-tenant + hardening per scale (Redis cache, rate limiter)

## Next Action Items
- Backend testing_agent run
- P1 features based on user priorities
