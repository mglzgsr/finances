# Finance Dashboard

Dashboard personal de finanzas con soporte para múltiples cuentas bancarias vía **TrueLayer Open Banking** y CSV. Self-hosted en LXC. PWA instalable desde el navegador.

## Stack

- **Backend**: FastAPI (Python) + SQLite
- **Frontend**: HTML/JS vanilla + Chart.js — PWA instalable
- **Open Banking**: TrueLayer (Lloyds, HSBC, AMEX y otros)
- **Deploy**: systemd + GitHub Actions self-hosted runner
- **Acceso externo**: Cloudflare Zero Trust Tunnel

## Estructura

```
finances/
├── main.py              ← FastAPI app + endpoints
├── database.py          ← SQLite: transacciones, cuentas, conexiones
├── open_banking.py      ← TrueLayer OAuth2 + fetch de datos
├── parsers.py           ← Parsers CSV (Lloyds, HSBC)
├── requirements.txt
├── frontend/
│   └── index.html       ← Dashboard PWA (single-page app)
├── static/
│   ├── manifest.json    ← PWA manifest
│   ├── service-worker.js
│   ├── icon-192.png
│   ├── icon-512.png
│   └── apple-touch-icon.png
└── .github/
    └── workflows/
        └── deploy.yml   ← CI/CD: pull + restart en push a main
```

## Funcionalidades

- **Multi-cuenta**: selector de cuentas en el header (Lloyds, HSBC, AMEX...)
- **Open Banking**: conexión OAuth con TrueLayer, sync automático vía cron
- **Importación CSV**: histórico ilimitado para Lloyds y HSBC
- **Deduplicación**: evita duplicados al combinar CSV y TrueLayer
- **KPIs mensuales**: ingresos, gastos, balance, saldo actual
- **Gráfico de flujo**: evolución mensual de ingresos vs gastos
- **Categorías**: automáticas + edición manual desde la UI
- **Drill-down**: clic en categoría o KPI → lista de transacciones
- **Modo oscuro/claro**: persistente en localStorage
- **PWA**: instalable en iOS (Safari → Añadir a pantalla de inicio) y Android
- **Gestión de cuentas**: añadir, eliminar (con o sin transacciones)
- **Reset completo**: borrar toda la base de datos desde ajustes

## Cuentas soportadas

| Banco | Tipo | Fuente |
|-------|------|--------|
| Lloyds | Cuenta corriente | CSV + TrueLayer |
| HSBC | Cuenta corriente / ahorro | CSV + TrueLayer |
| AMEX | Tarjeta de crédito | TrueLayer (`/cards`) |

> TrueLayer no soporta hipotecas ni cuentas en USD actualmente.

## Infraestructura

- **Repo producción**: `/opt/finances` (rama `main`)
- **Servicio**: `finance-dashboard` (systemd)
- **Puerto**: 8000
- **DB**: `/opt/finances/finance.db`
- **URL**: `https://finances.mglzgsr.com`

## Deploy

El deploy es automático: cada push a `main` lanza el runner de GitHub Actions que hace `git pull` y reinicia el servicio.

Para deploy manual en el servidor:
```bash
cd /opt/finances && git pull && sudo systemctl restart finance-dashboard
```

## Configuración

Variables de entorno en `/opt/finances/.env`:

```env
TRUELAYER_CLIENT_ID=...
TRUELAYER_CLIENT_SECRET=...
TRUELAYER_REDIRECT_URI=https://finances.mglzgsr.com/callback
TRUELAYER_SANDBOX=false
```

## Conectar un banco

1. Abre la app → **+ Añadir banco**
2. Introduce el nombre del banco
3. Completa el flujo OAuth de TrueLayer
4. En iOS: cierra Safari y vuelve a la app desde la pantalla de inicio
5. Pulsa **Sincronizar**

## Privacidad

- Los CSVs no se almacenan — solo los datos parseados en SQLite
- La base de datos está en el servidor, excluida del repo
- El acceso está protegido por Cloudflare Zero Trust
