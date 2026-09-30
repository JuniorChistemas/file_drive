# file_drive — document-worker

Worker de procesamiento de documentos que se autentica contra **Google Drive** mediante una *service account*, navega la jerarquía de carpetas `RAÍZ/Manzana/DNI_LOTE`, agrupa las carpetas por **LOTE**, descarga los PDFs de cada lote y los comprime localmente con **Ghostscript** (perfil `/ebook`, 150 dpi) en `storage/temp/{LOTE}/{DNI}/`. Después consulta el **ERP** por lote, crea los `lot_assignments` y sube los PDFs comprimidos como documentos del contrato.

No es una aplicación web: es un proceso demonio en contenedor, sin framework, sin base de datos y sin endpoints HTTP. La autenticación es OAuth2 server-to-server (service account de Google) para Drive y bearer token (login usuario/password) para el ERP.

## Estado del proyecto

| Funcionalidad | Estado |
|---|---|
| Autenticación con service account (`drive.readonly`) | ✅ Operativa |
| Navegación de carpetas (raíz → manzana → lotes) | ✅ Operativa |
| Listado de PDFs con paginación | ✅ Operativa |
| Descarga en streaming (chunks de 1 MB) | ✅ Operativa |
| Compresión con Ghostscript (`/ebook`) | ✅ Operativa |
| Agrupación por LOTE (parse de `DNI_LOTE`) | ✅ Operativa |
| Integración ERP (login, consulta por lote, lot-assignments, assignment-documents) | ✅ Operativa |
| Apagado graceful (SIGTERM/SIGINT) | ✅ Operativa |
| Subida/reemplazo en Drive | ⏳ Pendiente (requiere scope `drive`) |
| Ciclo de vida `processed/failed/duplicated` | ⏳ Pendiente (constantes definidas, sin uso) |
| Worker de escaneo periódico | ⏳ Pendiente (hoy: pipeline único al arranque + espera) |

Evidencia operacional: corrida completa exitosa de 51/51 PDFs comprimidos con 0 errores (`logs/app.log`, 2026-07-23).

> **Nota sobre el estado de git:** el commit `v1` (init) contiene solo autenticación y listado. La funcionalidad de descarga y compresión (~280 líneas + 12 tests: `app/drive/files.py`, `app/pdf/`, `find_lote_folder`, tests de files/compress) está completa en el árbol de trabajo pero **aún sin commitear**.

## Pipeline

1. **Login ERP**: `POST /api/auth/login` con `ERP_USERNAME`/`ERP_PASSWORD` → bearer token. Si falla (o falta `ERP_API_URL`), se procesa solo local sin subir.
2. **Scan Drive**: raíz → manzana → carpetas `DNI_LOTE` (ej. `73439516_A-19`), agrupadas por LOTE (split en el primer `_`). Nombres inválidos → warning + skip.
3. **Por cada LOTE**:
   - Descarga + compresión de cada PDF en `storage/temp/{LOTE}/{DNI}/`.
   - `GET /api/search/contract?lot_name={LOTE}` (bearer token + header `X-API-Token` con `ERP_API_KEY`) → `lot_id` + contratos (1 por DNI).
   - Diff de DNIs ERP vs carpetas locales: warnings **FALTA** (contrato sin carpeta) y **SOBRA** (carpeta sin contrato).
   - Por cada contrato con carpeta local: `POST /api/panel/lot-assignments` (`customer_id`, `lot_id`) → `lot_assignments_id`; si no existe la carpeta → warning + continue.
   - Por cada PDF comprimido: `POST /api/panel/assignment-documents` (multipart: `lot_assignments_id`, `document_type_id`, `file`, `status=pending`). El `document_type_id` se deduce del nombre del archivo (`app/erp/doctypes.py`); tipos desconocidos (p. ej. TRASPASO) → OTROS. Cada subida es **síncrona**: el POST espera a que el backend termine de procesar el archivo (timeout de 5 min, `ERP_UPLOAD_TIMEOUT`) antes de continuar con el siguiente documento/carpeta.
4. **Resumen final**: contratos subidos/omitidos, documentos subidos/fallidos y lotes fallidos (si los hay).

Ningún error de archivo o de API corta el batch: todo fallo se loguea (warning/exception) y se continúa. El listado de Drive reintenta los errores transitorios (500/502/503/429) con backoff (`DRIVE_NUM_RETRIES`); un fallo de una carpeta DNI se aísla sin perder el resto del lote, y un fallo de un lote no detiene los siguientes.

**Reanudación tras una corrida interrumpida**: los comprimidos de `storage/temp/{LOTE}/{DNI}/` se reutilizan (no se re-descargan ni re-comprimen). Como el ERP no deduplica `lot_assignments`, para no duplicar lotes ya subidos se define `PIPELINE_START_FROM_LOTE` con el primer lote pendiente (inclusive); los comprimidos ya hechos se reaprovechan automáticamente. ⚠️ Si un lote falló *a mitad* de su fase ERP, verificar en `logs/app.log` qué contratos ya se subieron antes de reprocesarlo (el resumen final lista los lotes fallidos).

## Arquitectura

```
app/main.py             Orquestación: pipeline Drive → compresión → ERP, señales
app/pipeline.py         Helpers puros: parse DNI_LOTE, agrupar por lote, diff de contratos
app/config/settings.py  Configuración tipada (Pydantic BaseSettings + .env)
app/config/constants.py Scopes, MIME, layout de storage, parámetros Ghostscript
app/drive/client.py     Fábrica del servicio Drive autenticado (service account)
app/drive/folders.py    Navegación: búsqueda, resolución de rutas, iteradores paginados
app/drive/files.py      Descarga streaming (MediaIoBaseDownload, 1 MB)
app/pdf/compress.py     Compresión local con Ghostscript (subprocess)
app/erp/client.py       Cliente HTTP del ERP (httpx): login + endpoints autenticados
app/erp/doctypes.py     Mapping filename → document_type_id
app/storage/            Layout de estados: temp / processed / failed / duplicated
```

- Inyección de dependencia manual: las funciones de `drive/` y `pdf/` reciben `service`/paths como argumentos, lo que permite testearlas con fakes sin red.
- Fail-fast en configuración: al construir `Settings` se valida que el archivo de credenciales exista, sea JSON válido y sea de tipo `service_account`.
- Logging con `loguru`: stdout (INFO) + archivo rotativo `logs/app.log` (DEBUG, 10 MB, 7 días).
- Manejo de errores por archivo: si un PDF falla, se loguea y se continúa con el batch.

## Requisitos

- **Python 3.13** (imagen Docker) o 3.12+ local.
- **Ghostscript** (`gs`) instalado en el sistema (la imagen Docker ya lo incluye vía apt).
- Una **service account** de Google Cloud con la clave JSON, y la carpeta raíz de Drive compartida con su `client_email`.
- Dependencias: `pip install -r requirements.txt`.

## Configuración

Copiar `.env.example` a `.env` y completar:

| Variable | Obligatoria | Descripción |
|---|---|---|
| `GOOGLE_CREDENTIALS_PATH` | Sí | Ruta al JSON de la service account (en Docker: `/app/credentials/google-service-account.json`) |
| `DRIVE_ROOT_FOLDER` | No | Nombre de la carpeta raíz en Drive (default: `CARPETA_PRUEBA`) |
| `DRIVE_MANZANA_FOLDER` | No | Nombre de la manzana dentro de la raíz (default: `Manzana A`) |
| `ERP_API_URL` | No | URL base de la API del ERP (vacío = solo procesamiento local) |
| `ERP_API_KEY` | No | API key del ERP (header `X-API-Token` en `/api/search/contract`) |
| `ERP_USERNAME` | No | Usuario del login ERP (default: `admin`) |
| `ERP_PASSWORD` | No | Password del login ERP |
| `PIPELINE_START_FROM_LOTE` | No | Lote desde el cual procesar (inclusive); vacío = todos. Para reanudar una corrida interrumpida sin duplicar `lot_assignments` ya subidos (el ERP no deduplica) |
| `LOG_LEVEL` | No | Nivel de logging (default: `INFO`) |

Colocar la clave de la service account en `credentials/google-service-account.json`. Ni `.env` ni `credentials/*.json` están trackeados en git ni entran al build de Docker (entran en runtime por `env_file` y bind mount).

> La service account solo ve las carpetas compartidas con su `client_email`. Si la carpeta raíz no aparece, verificar el sharing.

## Uso

### Docker (forma prevista)

```bash
docker compose up --build -d          # levanta el servicio document-worker
docker compose logs -f document-worker
docker compose down                   # envía SIGTERM → apagado graceful
```

### Local

```bash
pip install -r requirements.txt
python -m app.main
```

Requiere Ghostscript en el sistema y ejecutar desde la raíz del proyecto (el log se escribe en la ruta relativa `logs/app.log`).

## Tests

59 tests unitarios en `tests/`, con fakes en memoria (cero llamadas de red):

- `test_folders.py` — navegación: búsqueda, resolución de rutas, lotes, paginación, nombres con comillas.
- `test_files.py` — descarga: escritura, directorios anidados, validación de mimeType.
- `test_compress.py` — compresión con PDFs reales generados por PyMuPDF (se salta automáticamente si no hay `gs` en el sistema).
- `test_pipeline.py` — parse de `DNI_LOTE`, agrupación por lote, diff de contratos.
- `test_doctypes.py` — filename → `document_type_id` (incluye fallback a OTROS).
- `test_erp_client.py` — login, consulta por lote, lot-assignments y upload multipart con `httpx.MockTransport`.

```bash
pip install -r requirements.txt
pytest
```

> Nota: `.dockerignore` excluye `tests/`, por lo que los tests no corren dentro de la imagen Docker tal cual está hoy.

## Estructura del repositorio

```
.
├── app/
│   ├── main.py            # Punto de entrada (python -m app.main)
│   ├── pipeline.py        # Helpers puros del pipeline (parse, group, diff)
│   ├── config/            # Settings + constantes
│   ├── drive/             # Cliente, carpetas y descarga de Drive
│   ├── pdf/               # Compresión con Ghostscript
│   ├── erp/               # Cliente HTTP del ERP + mapping de document_type
│   └── storage/           # temp/ processed/ failed/ duplicated/
├── credentials/           # Clave JSON de la service account (no trackeado)
├── logs/                  # app.log (rotativo)
├── tests/                 # pytest (fakes, sin red)
├── .env.example           # Plantilla de configuración
├── Dockerfile             # python:3.13-slim + ghostscript, usuario no-root
├── docker-compose.yml     # Servicio document-worker + bind mounts
└── requirements.txt       # Dependencias
```

## Limitaciones conocidas y roadmap

1. **Worker esqueleto:** tras el pipeline inicial el proceso queda en espera (bucle de 30 s). Falta el scan periódico, cola y reintentos reales.
2. **Subida a Drive pendiente:** el scope actual es `drive.readonly`; subir/reemplazará archivos requerirá cambiar a `.../auth/drive`.
3. **Ciclo de vida de archivos incompleto:** ni el original ni el comprimido se mueven a `processed/`/`failed/`/`duplicated/`; `temp/{LOTE}/{DNI}/` crece indefinidamente en corridas largas.
4. **`gs` sin timeout:** un Ghostscript colgado bloquearía el worker (añadir `timeout` al subprocess).
5. **Reintentos parciales:** la API de Drive reintenta errores transitorios (5xx, 429) vía `num_retries`; las llamadas al ERP siguen sin reintentos/backoff.
6. **Dependencias sin uso aún:** `tenacity`, `python-dateutil` (reservadas para reintentos/fechas).
7. **Sin CI ni linting configurado** (no hay ruff/black/mypy, GitHub Actions, ni coverage).
