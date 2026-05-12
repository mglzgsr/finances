# Finance Dashboard — CLAUDE.md

Dashboard personal de finanzas. FastAPI + SQLite + HTML/JS vanilla. PWA instalable.

## Infraestructura
- **Producción**: `/opt/finances`, servicio `finance-dashboard`, puerto 8000, `finances.mglzgsr.com`
- **Dev**: `/opt/finances-dev`, servicio `finance-dashboard-dev`, puerto 8001, `dev-finances.mglzgsr.com`
- **Deploy**: push a `main` → GitHub Actions runner (self-hosted) → `git pull` + `pip install` + `systemctl restart finance-dashboard`
- **DB**: `data/finance.db` relativo al script; override con env var `DB_PATH`
- **Acceso**: Cloudflare Zero Trust Tunnel (single-user, sin login propio)
- Sin Docker en producción — venv directo en LXC (el `Dockerfile` existe pero no se usa en prod)

## Archivos clave
- `main.py` — FastAPI app, todos los endpoints
- `database.py` — SQLite: init, queries, funciones de acceso
- `open_banking.py` — TrueLayer OAuth2, fetch de cuentas/tarjetas/transacciones
- `parsers.py` — parsers CSV para Lloyds y HSBC; `CATEGORY_RULES` hardcodeadas en español
- `frontend/index.html` — SPA completa (HTML + CSS + JS en un solo archivo)
- `static/` — manifest.json, service-worker.js, iconos PWA

## Base de datos — tablas
- **transactions**: `id, date, description, tx_type, is_debit, amount, balance, category, bank, hash, timestamp, account_id`
- **accounts**: `id, slug, display_name, account_type, currency, source, connection_id, truelayer_account_id, current_balance, last_sync, is_active, sort_order`
- **bank_connections**: `bank, access_token, refresh_token, expires_at, connected_at, last_sync, current_balance`
- **settings**: key/value — incluye `initial_balance_hsbc`

> No existe tabla `categories` — las categorías disponibles son la unión de `CATEGORY_RULES.keys()` + categorías distintas en `transactions` + `"Otros"`, devueltas ordenadas por `GET /api/category-list`.

> `timestamp` y `account_id` se añadieron con `ALTER TABLE` — el bloque `try/except` en `init_db()` es intencional para compatibilidad con DBs existentes sin esas columnas.

## API endpoints
```
POST   /api/upload                              ← uno o más CSV; detecta banco automáticamente
GET    /api/accounts
POST   /api/accounts                            ← crear cuenta manual
DELETE /api/accounts/{slug}?delete_transactions=bool
DELETE /api/database                            ← reset completo (transacciones, cuentas y conexiones)
GET    /api/summary?year&month&bank
GET    /api/monthly-flow?months&bank
GET    /api/categories?year&month&bank
GET    /api/category-list
GET    /api/transactions?year&month&category&bank&is_debit&description&limit&offset
PATCH  /api/transactions/{id}/category          ← body: {category, apply_to_similar: bool}
GET    /api/balance?bank&year&month
GET    /api/connections
GET    /api/settings
PATCH  /api/settings
POST   /api/sync?bank                           ← sync TrueLayer; refresca token si caduca en <5 min
GET    /connect?bank                            ← inicia OAuth
GET    /callback                                ← callback OAuth → devuelve HTML (no redirect)
```

## TrueLayer Open Banking
- Credenciales live en `.env` (`TRUELAYER_SANDBOX=false`)
- SCOPES: `accounts transactions balance cards offline_access`
- `fetch_accounts()` → `/data/v1/accounts`; `fetch_cards()` → `/data/v1/cards` (AMEX)
- AMEX solo funciona con `fetch_cards()` — `/data/v1/accounts` devuelve 501 para tarjetas, comportamiento esperado de TrueLayer
- Auto-discovery en `/callback` y en cada `/api/sync`: `create_account()` usa `INSERT OR REPLACE` → idempotente
- Slug generado como `{connection_id}-{display_name}-{currency}` minúsculas, caracteres no alfanuméricos → guiones
- Balance cuentas: campo `available` con fallback a `current`; tarjetas: campo `current` = deuda pendiente
- Token refresh automático en `/api/sync` si caduca en menos de 5 minutos
- Tras OAuth en iOS: Safari no puede volver a la PWA — `/callback` devuelve una página HTML estática con instrucciones en lugar de hacer redirect

## Cuentas bancarias
- `lloyds` — cuenta personal (CSV + TrueLayer)
- `hsbc` — cuenta común (CSV + TrueLayer)
- `amex` — tarjeta de crédito (solo TrueLayer)
- HSBC hipoteca y USD: sin soporte TrueLayer (pendiente añadir como cuentas manuales)

## Deduplicación de transacciones
- Hash TrueLayer: MD5 de `tl|{tx_id}|{bank}` — campo `hash` con UNIQUE constraint
- Hash CSV Lloyds: MD5 de `{date}|{desc}|{amount}|{balance}`
- Hash CSV HSBC: MD5 de `{date}|{desc_original}|{amount}|""` — usa la descripción sin limpiar para el hash
- Soft-dedup en `save_transactions()`: comprueba `(date, description, amount, bank, is_debit)` antes de INSERT para cubrir colisiones entre CSV y TrueLayer de la misma transacción

## Parsers CSV
- Lloyds: detectado por presencia de `"transaction type"` y `"sort code"` en la primera línea
- HSBC: cualquier CSV que no sea Lloyds
- HSBC limpia sufijos del description (` )))`, ` VIS`, ` DD`, ` BP`, ` CR`, ` IM`) antes de guardar, pero usa el description original para el hash

## Frontend (index.html)
- `currentAccount` = slug seleccionado; `currentAccountMeta` = objeto completo con currency
- `currencySymbol()` → CURRENCY_SYMBOLS map (GBP→£, EUR→€, USD→$)
- Panel de transacciones (`catPanel`): se abre desde KPI gastos/ingresos y drilldown de categorías; carga hasta 500 transacciones
- Edición de categoría disponible desde panel de recientes Y desde `catPanel`: modal con `<select>` de categorías existentes + opción "＋ Nueva categoría..." que revela un `<input>` de texto; checkbox "Aplicar a todas las transacciones similares" llama a `PATCH` con `apply_to_similar=true`; muestra lista de transacciones con la misma `description` si hay más de una
- `categoryListCache` se invalida al guardar una categoría nueva
- Settings modal (⚙): tema, subir CSV, saldo inicial HSBC, zona de peligro (borrar DB requiere escribir "BORRAR")
- Eliminar cuenta: botón 🗑 junto al selector → modal con opción de borrar o no las transacciones
- Responsive: breakpoints 768px y 430px
- PWA en iOS: Safari → Compartir → "Añadir a pantalla de inicio"

## Balance
- Prioridad: `current_balance` en `accounts` (actualizado por TrueLayer sync) → `running_balance` en transacciones → fallback con `initial_balance_{bank}` + suma neta
- Balance NO hereda saldo de otro banco — bug corregido en commit `29af879`, antes hacía fallback a `initial_balance_hsbc` para cualquier banco sin balance

## Decisiones técnicas
- CSV para histórico >90 días; TrueLayer para sync diario (limitado a 90 días por la API)
- CORS solo permite `192.168.x.x` y `localhost` — en prod, Cloudflare hace forward al puerto 8000 en la misma máquina, sin CORS cross-domain
- Categorías editadas manualmente en `transactions.category` se pierden al reimportar el mismo CSV (el parser reasigna la categoría desde `CATEGORY_RULES`)

## Pendiente
- Cuentas manuales para HSBC USD e hipoteca
- AMEX en cron de sync automático
- Proteger categorías editadas manualmente al reimportar CSV
- Excluir transferencias internas Lloyds↔HSBC de totales de gastos/ingresos
