# CleanTec - PRD (updated 24 Apr 2026)

## Problem
Industrial laundry **commercial SaaS** — ERP focalizzato sul flusso commerciale: Clienti → Articoli → Listini → D.D.T. → Fatture → Sospesi. Multi-tenant con abbonamenti Stripe e self-service onboarding.

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
- (TEST) Eseguire `testing_agent_v3_fork` per validare E2E il flusso commerciale post-refactor (in attesa di conferma utente)
- Configurare Stripe LIVE key in produzione
- (Opzionale) Aggiornare copy landing/marketing per messaggio "ERP commerciale"
