# Finance Dashboard — Context

## Stack
- FastAPI + SQLite + Python (venv directo en LXC, sin Docker)
- Frontend HTML/JS vanilla + Chart.js (PWA)
- GitHub Actions self-hosted runner para CI/CD (deploy automático en push a main)
- Cloudflare Zero Trust Tunnel para acceso externo con login
- Dominio: finances.mglzgsr.com

## Funcionalidades implementadas
- Parsers CSV para Lloyds y HSBC (detección automática de banco)
- Deduplicación por hash MD5
- Switcher Lloyds / HSBC — dashboards independientes por banco
- Balance real: Lloyds lee la columna balance del CSV, HSBC desde saldo inicial configurable
- KPI mensual: saldo inicio y fin de mes
- Drill-down de categorías (clic → panel de transacciones)
- Drill-down de ingresos y gastos (KPI clickable)
- Reclasificación de categorías desde la UI (✏️ en cada transacción)
- Modo oscuro / claro con persistencia en localStorage
- SQL injection corregido (queries parametrizadas)
- CORS restringido a 192.168.0.x y localhost

## Infraestructura LXC
- Repo en: /opt/finances
- Venv en: /opt/finances/venv
- Usuario del servicio: finances
- Servicio systemd: finance-dashboard
- Runner GitHub Actions: actions.runner.mglzgsr-finances.finances.service

## Siguiente paso: TrueLayer Open Banking
- Cuenta TrueLayer creada con credenciales sandbox y live
- Redirect URI: https://finances.mglzgsr.com/callback
- Plan:
  - open_banking.py — OAuth2 + fetch transacciones
  - Endpoints: /connect, /callback, /sync
  - Sync diario automático (scheduler o cron)
  - Botón "Connect bank" en el dashboard
  - Tokens en SQLite (tabla bank_connections)
  - Credenciales via .env — .env.example en el repo, .env en .gitignore

## Decisiones tomadas
- CSV sigue como importación histórica (TrueLayer solo da 90 días)
- Categorías en español, hardcodeadas en parsers.py con edición manual desde UI
- El hash de deduplicación incluye date|description|amount|balance
- Categorías editadas manualmente se pierden si se reimporta el mismo CSV (pendiente proteger)
- Transferencias internas Lloyds↔HSBC no se excluyen de totales (pendiente)
