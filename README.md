# Finance Dashboard

Dashboard personal de finanzas para extractos de **Lloyds** y **HSBC UK**.  
Self-hosted en QNAP (o cualquier máquina con Docker). PWA instalable desde el browser.

## Stack

- **Backend**: FastAPI (Python) + SQLite
- **Frontend**: HTML/JS + Chart.js (PWA)
- **Deploy**: Docker Compose

## Estructura

```
projects/finances/
├── backend/
│   ├── main.py          ← FastAPI app
│   ├── parsers.py       ← Parsers Lloyds / HSBC
│   ├── database.py      ← SQLite
│   └── requirements.txt
├── frontend/
│   ├── index.html       ← Dashboard PWA
│   ├── manifest.json
│   └── service-worker.js
├── data/                ← SQLite persiste aquí (no se sube a git)
├── docker-compose.yml
├── Dockerfile
└── .gitignore
```

## Inicio rápido

### Con Docker (recomendado para QNAP)

```bash
git clone https://github.com/TU_USUARIO/finances.git
cd finances
docker-compose up -d
```

Abre [http://localhost:8000](http://localhost:8000)

### Local (desarrollo)

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

## Uso

1. Abre el dashboard
2. Pulsa **Subir CSV** y arrastra tus extractos (Lloyds y/o HSBC)
3. Los datos se guardan en SQLite — los duplicados se ignoran automáticamente
4. Filtra por mes desde el selector superior

## Categorías

Edita `backend/parsers.py` → `CATEGORY_RULES` para añadir o modificar categorías.

## QNAP — Container Station

1. Sube la carpeta al QNAP (via File Station o SSH)
2. Abre Container Station → Crear → Desde `docker-compose.yml`
3. Mapea el puerto 8000
4. Asegúrate de que el volumen `./data` apunta a una carpeta persistente

## Privacidad

- Los CSVs no se almacenan, solo los datos parseados en SQLite
- La base de datos está en `./data/` — excluida del repo vía `.gitignore`
- No hay conexión a servicios externos
