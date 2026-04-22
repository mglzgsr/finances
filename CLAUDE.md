# Finance Dashboard — CLAUDE.md

Dashboard personal de finanzas. FastAPI + SQLite + HTML/JS vanilla. PWA instalable.

## Infraestructura
- **Producción**: `/opt/finances`, servicio `finance-dashboard`, puerto 8000, `finances.mglzgsr.com`
- **Dev**: `/opt/finances-dev`, servicio `finance-dashboard-dev`, puerto 8001, `dev-finances.mglzgsr.com`
- **Deploy**: push a `main` → GitHub Actions runner → `git pull` + `systemctl restart finance-dashboard`
- **DB producción**: `/opt/finances/finance.db`
- **Acceso**: Cloudflare Zero Trust Tunnel (single-user, sin login propio)

## Archivos clave
- `main.py` — FastAPI app, todos los endpoints
- `database.py` — SQLite: init, queries, funciones de acceso
- `open_banking.py` — TrueLayer OAuth2, fetch de cuentas/tarjetas/transacciones
- `parsers.py` — parsers CSV para Lloyds y HSBC
- `frontend/index.html` — SPA completa (HTML + CSS + JS en un solo archivo)
- `static/` — manifest.json, service-worker.js, iconos PWA

## Base de datos — tablas
- **transactions**: `date, description, tx_type, is_debit, amount, balance, category, bank, hash, timestamp, account_id`
- **accounts**: `slug, display_name, account_type, currency, source, connection_id, truelayer_account_id, current_balance, last_sync, is_active, sort_order`
- **bank_connections**: `bank, access_token, refresh_token, expires_at, last_sync, current_balance`
- **settings**: key/value — incluye `initial_balance_hsbc` y overrides de categorías

> No existe tabla `categories` — los overrides de categoría se guardan en `settings`.

## API endpoints
```
POST   /api/upload                              ← subir CSV
GET    /api/accounts                            ← lista cuentas
POST   /api/accounts                            ← crear cuenta manual
DELETE /api/accounts/{slug}?delete_transactions=bool
DELETE /api/database                            ← reset completo (borra todo)
GET    /api/summary?year&month&bank
GET    /api/monthly-flow?months&bank
GET    /api/categories?year&month&bank
GET    /api/category-list                       ← lista de categorías disponibles
GET    /api/transactions?year&month&category&bank&is_debit&limit&offset
PATCH  /api/transactions/{id}/category
GET    /api/balance?bank&year&month
GET    /api/connections                         ← estado OAuth por banco
GET    /api/settings
PATCH  /api/settings
POST   /api/sync?bank                           ← sync TrueLayer
GET    /connect?bank                            ← iniciar OAuth
GET    /callback                                ← callback OAuth → devuelve HTML (no redirect)
```

## TrueLayer Open Banking
- Credenciales live en `.env` (`TRUELAYER_SANDBOX=false`)
- SCOPES: `accounts transactions balance cards offline_access`
- `fetch_accounts()` → cuentas corrientes/ahorro; `fetch_cards()` → tarjetas (AMEX)
- Auto-discovery en `/callback`: crea entradas en `accounts` automáticamente
- Balance: campo `available` con fallback a `current`
- AMEX usa `/data/v1/cards` (no `/accounts`) — error 501 esperado en `/accounts`
- Tras OAuth en iOS: Safari no puede volver a la PWA — la página de callback muestra "Cierra Safari y abre la app desde la pantalla de inicio"

## Cuentas bancarias
- `lloyds` — cuenta personal (CSV + TrueLayer)
- `hsbc` — cuenta común (CSV + TrueLayer)
- `amex` — tarjeta de crédito (solo TrueLayer)
- HSBC hipoteca y USD: sin soporte TrueLayer (pendiente añadir como cuentas manuales)

## Deduplicación de transacciones
- Hash TrueLayer: `tl|{tx_id}|{bank}`
- Hash CSV Lloyds: `{date}|{desc}|{amount}|{balance}`
- Soft-dedup en `save_transactions()`: comprueba `(date, description, amount, bank, is_debit)` antes de INSERT

## Frontend (index.html)
- `currentAccount` = slug seleccionado; `currentAccountMeta` = objeto completo con currency
- `currencySymbol()` → CURRENCY_SYMBOLS map (GBP→£, EUR→€, USD→$)
- Settings modal (⚙): tema, subir CSV, saldo inicial HSBC, zona de peligro (borrar DB requiere escribir "BORRAR")
- Eliminar cuenta: botón 🗑 junto al selector → modal con opción de borrar o no las transacciones
- Responsive: breakpoints 768px y 430px
- PWA en iOS: Safari → Compartir → "Añadir a pantalla de inicio" (no hay "Instalar app")

## Decisiones técnicas importantes
- CSV para histórico >90 días; TrueLayer para sync diario
- Balance usa `current_balance` de `accounts` si existe; si no, calcula desde transacciones con `id ASC`
- Balance NO hereda saldo de otro banco (bug corregido — antes hacía fallback a `initial_balance_hsbc`)
- Categorías en español, hardcodeadas en `parsers.py`; editables desde la UI
- Sin Docker — venv directo en LXC

## Pendiente
- Cuentas manuales para HSBC USD e hipoteca
- AMEX en cron de sync automático
- Proteger categorías editadas al reimportar CSV
- Excluir transferencias internas Lloyds↔HSBC de totales
