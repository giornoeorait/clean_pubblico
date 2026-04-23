# CleanTec - PRD

## Original Problem
Build "CleanTec" - integrated ERP+MES+WMS+TMS SaaS for industrial laundry.
Full multi-tenant self-service SaaS with Stripe subscriptions.

## Stack
- Backend: FastAPI + Motor + MongoDB (maxPoolSize=200)
- Frontend: React 19 + Tailwind + Shadcn/UI + Phosphor Icons + Recharts
- Auth: JWT (Bearer + cookie) with tenant_id in claims
- i18n (IT default)
- Object Storage: Emergent Object Storage (EMERGENT_LLM_KEY)
- Notifications: Twilio (optional) + stub fallback
- Payments: Stripe via emergentintegrations

## Multi-tenant SaaS (23 Apr 2026)
- Collection `tenants`: slug, piano, stato (trial|active|past_due|canceled|suspended), trial_ends_at, limits, usage, stripe_*
- Every data collection carries `tenant_id` enforced via `tenant_scope(user)` / `merge_scope` / `inject_tenant` helpers in core.py
- JWT token includes tenant_id for O(1) auth+scoping
- Self-service registration at `/register` creates tenant + admin user + 14-day trial (no card)
- Public pricing page at `/pricing` with monthly/annual toggle (annual = -17%)
- Admin billing page at `/billing` with plan switcher, Stripe checkout, payment history
- Trial banner on every page showing days remaining
- Backfill migration: all legacy data assigned to DEMO_TENANT_ID

## Plans (server-side authoritative)
| Piano | Mensile | Annuale (/mese) | Utenti | Lotti/mese | SMS |
|-------|---------|-----------------|--------|-----------|------|
| Starter | €59 | €49 | 5 | 1.000 | 0 |
| Pro (raccomandato) | €179 | €149 | 20 | 10.000 | 100 |
| Enterprise | €449 | €379 | ∞ | ∞ | 500 |

Trial: **14 giorni**, no card required.

## Core Features (cumulative)
### Ops
- Clienti/Articoli/Macchine/Utenti CRUD
- Accettazione → Ritiri → Lotti (9 stati)
- MES Kanban + Controllo Qualità + Logistica + Fatturazione

### Add-ons (P1 complete)
- Magazzino detergenti/DPI con scorte minime
- Manutenzione macchine con ticket + interventi
- Object Storage (foto + firme digitali)
- Notifiche SMS/WhatsApp (Twilio + stub)
- Hardware ingestion REST (barcode, bilancia, RFID)

### Interfaces
- Dashboard, Touch (tablet), Mobile (autisti), Portale Cliente

## Stripe Integration
- `POST /api/subscriptions/checkout` — crea sessione Stripe (monthly|annual)
- `GET /api/subscriptions/status/{session_id}` — polling post-return
- `POST /api/webhook/stripe` — webhook handler
- `GET /api/subscriptions/transactions` — storico
- Collezione `payment_transactions` con tenant_id + session_id + plan_id + billing_cycle + status
- Env: `STRIPE_API_KEY=sk_test_emergent` (già in .env)

## Security
- Every write endpoint enforces `tenant_id` filter via `merge_scope(user, {...})`
- JWT carries tenant_id; mismatch = 404 on queries (data invisible)
- Rate limit naive su `/tenants/register` (5/min/IP)
- Password policy: min 8 chars
- Plan enforcement ready via `require_active_tenant()` (to be wired progressively)

## Demo credentials (DEMO tenant, shared across agent testing)
| Email | Password | Role |
|-------|----------|------|
| admin@cleantec.it | admin123 | admin |
| produzione@cleantec.it | produzione123 | produzione |
| logistica@cleantec.it | logistica123 | logistica |
| qualita@cleantec.it | qualita123 | qualita |
| contabilita@cleantec.it | contabilita123 | contabilita |
| cliente@cleantec.it | cliente123 | cliente → Hotel Excelsior Roma |
| owner@lavtest.it | segretaPWD1! | NEW tenant (Pro trial) |

## Backlog (P2)
- Plan limit enforcement in CREATE endpoints (block if over quota)
- Email verification flow
- Stripe Customer Portal (update card, download invoices) — richiede Stripe full SDK
- Superadmin dashboard (MRR, churn, tenants list)
- BI reporting avanzato
- Inventario biancheria noleggio per cliente
- Short-lived signed URLs per /api/files (HMAC invece di `?auth=`)
- TTL index `db.hardware_events` (retention)
- SDI fatturazione elettronica italiana XML
- 2FA OTP
- Test regression multi-tenant isolation con testing agent

## Next Action Items
- Run testing_agent_v3 to validate multi-tenant isolation + Stripe flow
- Wire plan limit enforcement on create endpoints (users, lotti)
- Admin side: superadmin dashboard
