# Finance Dashboard — Context

## Stack
- FastAPI + SQLite + Python (venv directo en LXC, sin Docker)
- Frontend HTML/JS vanilla + Chart.js (PWA instalable)
- GitHub Actions self-hosted runner para CI/CD (deploy automático en push a main)
- Cloudflare Zero Trust Tunnel para acceso externo con login
- Dominio producción: finances.mglzgsr.com
- Dominio dev: dev-finances.mglzgsr.com → puerto 8001

## Infraestructura LXC
- Repo producción: /opt/finances (rama main)
- Repo dev: /opt/finances-dev (git worktree, rama feature/multi-account mergeada en main)
- Venv producción: /opt/finances/venv
- Venv dev: /opt/finances-dev/venv
- Usuario del servicio: finances
- Servicio producción: finance-dashboard (systemd)
- Servicio dev: finance-dashboard-dev (systemd, puerto 8001)
- Runner GitHub Actions: actions.runner.mglzgsr-finances.finances.service
- DB producción: /opt/finances/finance.db
- DB dev: /opt/finances-dev/finance_dev.db

## Cuentas bancarias soportadas
- **lloyds** — cuenta personal (CSV + TrueLayer)
- **hsbc** — cuenta común (CSV + TrueLayer)
- **amex** — tarjeta de crédito (TrueLayer, endpoint /cards)
- HSBC también tiene: hipoteca, global account (USD) — sin soporte TrueLayer aún
- Cuentas en tabla `accounts` con slugs generados automáticamente en OAuth callback

## TrueLayer Open Banking
- Credenciales live en .env (TRUELAYER_SANDBOX=false)
- SCOPES: accounts transactions balance cards offline_access
- Endpoints: /connect?bank=X, /callback (OAuth), /api/sync?bank=X
- Auto-discovery de cuentas y tarjetas en callback
- Tokens guardados en tabla bank_connections (access_token, refresh_token, expires_at)
- Cron sync diario: `/opt/finances/venv/bin/python /opt/finances/sync_cron.py`
- TrueLayer no soporta hipotecas (501 error esperado)
- AMEX usa /data/v1/cards (no /accounts)
- Balance: usa campo `available` con fallback a `current`

## Base de datos — tablas principales
- **transactions**: date, description, tx_type, is_debit, amount, balance, category, bank, hash, timestamp, account_id
- **accounts**: slug, display_name, account_type, currency, source, connection_id, truelayer_account_id, current_balance, last_sync, is_active, sort_order
- **bank_connections**: bank, access_token, refresh_token, expires_at, last_sync, current_balance
- **settings**: key/value (initial_balance_hsbc)
- **categories**: key/value overrides

## Deduplicación
- Hash MD5 primario: `tl|{tx_id}|{bank}` para TrueLayer
- Hash MD5 para CSV: `{date}|{desc}|{amount}|{balance}` (Lloyds), similar para HSBC
- Soft-dedup secundario en save_transactions(): comprueba (date, description, amount, bank, is_debit) antes de INSERT

## Frontend
- Selector de cuentas (`<select id="accountSelect">`) poblado desde /api/accounts
- currentAccount = slug, currentAccountMeta = objeto completo con currency
- currencySymbol() usa CURRENCY_SYMBOLS map (GBP→£, EUR→€, USD→$)
- Modo oscuro/claro con persistencia en localStorage
- Settings modal: contiene tema toggle + subir CSV
- Responsive: breakpoints 768px y 430px
- PWA: manifest.json + service-worker.js + apple-touch-icon 180x180

## PWA
- manifest.json: /static/manifest.json
- service-worker.js: /static/service-worker.js (caché assets, red para API)
- Iconos: icon-192.png, icon-512.png, apple-touch-icon.png en /static/
- En iOS: Safari → Compartir → Añadir a pantalla de inicio

## Decisiones técnicas
- CSV sigue como importación histórica (TrueLayer solo da 90 días)
- Categorías en español, hardcodeadas en parsers.py con edición manual desde UI
- Transferencias internas Lloyds↔HSBC no se excluyen de totales
- Orden de transacciones para balance: id ASC (TrueLayer inserta newest-first = id más bajo = más reciente)
- Balance en /api/balance: usa current_balance de accounts si está disponible, sino calcula desde transacciones

## API endpoints principales
- GET /api/accounts — lista de cuentas
- POST /api/accounts — crear cuenta manual
- GET /api/summary?year&month&bank — KPIs
- GET /api/transactions?year&month&category&bank&is_debit&limit&offset
- GET /api/monthly-flow?months&bank
- GET /api/categories?year&month&bank
- GET /api/balance?bank&year&month
- PATCH /api/transactions/{id}/category
- GET /api/connections — estado OAuth por banco
- POST /api/sync?bank — sincronizar TrueLayer
- GET /connect?bank — iniciar OAuth
- GET /callback — callback OAuth

## Pendiente / ideas futuras
- Cuentas manuales para HSBC USD y HSBC hipoteca
- Añadir AMEX al cron de sync automático
- Proteger categorías editadas manualmente al reimportar CSV
- Excluir transferencias internas de totales
