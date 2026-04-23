# CleanTec - PRD (updated 23 Apr 2026)

## Problem
Industrial laundry full-stack SaaS — ERP+MES+WMS+TMS, multi-tenant with Stripe subscriptions and self-service onboarding.

## Stack
- Backend: FastAPI + Motor + MongoDB (maxPoolSize=200)
- Frontend: React 19 + Tailwind + Shadcn/UI + Phosphor Icons + Recharts
- Auth: JWT with tenant_id in claims
- Storage: Emergent Object Storage
- Notifications: Twilio (optional) + stub fallback
- Payments: Stripe via emergentintegrations
- Email: stub (logged to db.email_events, ready for Resend/SendGrid)

## Implemented

### Core SaaS (this session)
- **Multi-tenant** complete: `tenants` collection + `tenant_id` on all 18 data collections. `tenant_scope`/`merge_scope`/`inject_tenant` helpers applied in every router. JWT carries tenant_id.
- **Self-service registration** `/register` + `/pricing` public page + 14-day trial (no card)
- **Stripe Subscriptions**: checkout (monthly/annual), webhook, polling status, transactions history
- **Cancel/Resume subscription**: access retained until current_period_end
- **Plan enforcement**: `require_active_tenant()` + `enforce_quota(user, 'users'|'lotti_monthly')` on critical POSTs. Returns 402 → frontend interceptor shows "Aggiorna piano" toast with redirect to /billing
- **Email verification stub**: verification_token on register, POST /api/auth/verify-email, resend endpoint, /verify page with status UI. Logs link in db.email_events (Resend-ready)
- **Superadmin dashboard** `/admin`: MRR/ARR, tenant count, conversion rate 90d, revenue this month, tenant distribution by plan/status, tenants list, transactions list. Role `superadmin` seeded as super@cleantec.it
- **BI Insights** `/insights`: linear-regression forecast kg/day (history 21d → predict 7d), consumi detergenti vs kg lavati, costo per kg, top consumi per articolo
- **Trial banner** global (red when ≤3 days) + **iPad swipe gesture** from left to open sidebar + `xl:` breakpoint for sticky sidebar

### Core app (cumulative)
- Clienti/Articoli/Macchine/Utenti CRUD
- Accettazione → Ritiri → Lotti (9 stati) → MES Kanban → Qualità → Logistica → Fatturazione
- Magazzino detergenti/DPI + Manutenzione macchine
- Object Storage (foto + firme)
- Notifiche SMS/WhatsApp (Twilio stub)
- Hardware ingestion (barcode/bilancia/RFID)
- Dashboard KPI, Touch tablet, Mobile autista, Portale Cliente

## Plans
| Piano | Mensile | Annuale | Utenti | Lotti/mese | SMS |
|-------|---------|---------|--------|-----------|------|
| Starter | €59 | €49 | 5 | 1.000 | 0 |
| Pro | €179 | €149 | 20 | 10.000 | 100 |
| Enterprise | €449 | €379 | ∞ | ∞ | 500 |

## Demo credentials
| Email | Password | Role |
|-------|----------|------|
| super@cleantec.it | Superadmin123! | **superadmin** |
| admin@cleantec.it | admin123 | admin (DEMO tenant) |
| produzione@cleantec.it | produzione123 | produzione |
| logistica@cleantec.it | logistica123 | logistica |
| qualita@cleantec.it | qualita123 | qualita |
| contabilita@cleantec.it | contabilita123 | contabilita |
| cliente@cleantec.it | cliente123 | cliente → Hotel Excelsior |
| owner@lavtest.it | segretaPWD1! | admin of Lavanderia Test Srl (Pro trial) |

## Architecture
- Backend routers (14): auth, users, catalog, operations, billing, dashboard, magazzino, manutenzione, files, notifications, hardware, tenants, subscriptions, superadmin, insights
- Frontend pages (25+): Dashboard, Clienti, Articoli, Macchine, Accettazione, Lotti, Produzione, Qualita, Logistica, Fatture, Magazzino, Manutenzione, Notifiche, Hardware, Utenti, Touch, Mobile, Portale, Pricing, Register, Billing, SuperAdmin, Insights, VerifyEmail, Login

## Testing status
- Iteration 1-7: core features
- Iteration 8: object storage + notifications + hardware (100% pass)
- Iteration 9 (today): quota enforcement + email verification + cancel/resume + superadmin + insights (17/17 backend, 4/4 frontend flows — 100%)

## Backlog (P2 / Future)
- 2FA OTP for admin accounts
- Stripe Customer Portal (update card, download invoices) — requires full Stripe SDK
- Fatturazione elettronica italiana SDI XML
- Inventario biancheria a noleggio per cliente (rotazione capi RFID)
- Short-lived signed URLs per /api/files (HMAC vs `?auth=` query param)
- TTL index db.hardware_events (retention)
- Resend/SendGrid integration for email verification
- Multi-sede warehouse per tenant Enterprise
- Webhook delivery receipts Twilio per Portale Cliente
- Onboarding wizard (import Excel, first ritiro)

## Next Action Items
- Configurare Resend API key per email verification reali (stub pronto)
- Configurare Stripe LIVE key in produzione (ora test)
- (Opzionale) Superadmin: CRUD manuale tenants, reset limits, force status
