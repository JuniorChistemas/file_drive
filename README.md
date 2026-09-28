# file_drive — document-worker

Worker de procesamiento de documentos que se autentica contra **Google Drive** mediante una *service account*, navega la jerarquía de carpetas `RAÍZ/Manzana/DNI_LOTE`, descarga los PDFs de cada lote y los comprime localmente con **Ghostscript** (perfil `/ebook`, 150 dpi).

No es una aplicación web: es un proceso demonio en contenedor, sin framework, sin base de datos y sin endpoints HTTP. La autenticación es OAuth2 server-to-server (service account de Google), no JWT ni sesiones.

## Estado del proyecto

| Funcionalidad | Estado |
|---|---|
| Autenticación con service account (`drive.readonly`) | ✅ Operativa |
| Navegación de carpetas (raíz → manzana → lotes) | ✅ Operativa |
| Listado de PDFs con paginación | ✅ Operativa |
| Descarga en streaming (chunks de 1 MB) | ✅ Operativa |
| Compresión con Ghostscript (`/ebook`) | ✅ Operativa |
| Apagado graceful (SIGTERM/SIGINT) | ✅ Operativa |
| Subida/reemplazo en Drive | ⏳ Pendiente (requiere scope `drive`) |
| Ciclo de vida `processed/failed/duplicated` | ⏳ Pendiente (constantes definidas, sin uso) |
| Integración ERP | ⏳ Pendiente (settings definidos, sin consumidor) |
| Worker de escaneo periódico | ⏳ Pendiente (hoy: smoke scan único + espera) |

Evidencia operacional: corrida completa exitosa de 51/51 PDFs comprimidos con 0 errores (`logs/app.log`, 2026-07-23).

> **Nota sobre el estado de git:** el commit `v1` (init) contiene solo autenticación y listado. La funcionalidad de descarga y compresión (~280 líneas + 12 tests: `app/drive/files.py`, `app/pdf/`, `find_lote_folder`, tests de files/compress) está completa en el árbol de trabajo pero **aún sin commitear**.

## Arquitectura

```
app/main.py             Orquestación: smoke scan, descarga+compresión por archivo, señales
app/config/settings.py  Configuración tipada (Pydantic BaseSettings + .env)
app/config/constants.py Scopes, MIME, layout de storage, parámetros Ghostscript
app/drive/client.py     Fábrica del servicio Drive autenticado (service account)
app/drive/folders.py    Navegación: búsqueda, resolución de rutas, iteradores paginados
app/drive/files.py      Descarga streaming (MediaIoBaseDownload, 1 MB)
app/pdf/compress.py     Compresión local con Ghostscript (subprocess)
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
| `ERP_API_URL` | No | Placeholder para la futura integración ERP |
| `ERP_API_KEY` | No | Placeholder para la futura integración ERP |
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

23 tests unitarios en `tests/`, con fakes en memoria (cero llamadas de red):

- `test_folders.py` — navegación: búsqueda, resolución de rutas, lotes, paginación, nombres con comillas.
- `test_files.py` — descarga: escritura, directorios anidados, validación de mimeType.
- `test_compress.py` — compresión con PDFs reales generados por PyMuPDF (se salta automáticamente si no hay `gs` en el sistema).

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
│   ├── config/            # Settings + constantes
│   ├── drive/             # Cliente, carpetas y descarga de Drive
│   ├── pdf/               # Compresión con Ghostscript
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

1. **Worker esqueleto:** tras el smoke scan inicial el proceso queda en espera (bucle de 30 s). Falta el scan periódico, cola y reintentos reales.
2. **Subida a Drive pendiente:** el scope actual es `drive.readonly`; subir/reemplazará archivos requerirá cambiar a `.../auth/drive`.
3. **Ciclo de vida de archivos incompleto:** ni el original ni el comprimido se mueven a `processed/`/`failed/`/`duplicated/`; `temp/` crece indefinidamente en corridas largas.
4. **Colisión de nombres:** dos lotes con un PDF homónimo se sobrescriben en `temp/` (pendiente de namespacing por lote).
5. **`gs` sin timeout:** un Ghostscript colgado bloquearía el worker (añadir `timeout` al subprocess).
6. **Sin reintentos/backoff en la API de Drive** pese a que `tenacity` ya está declarado en requirements.
7. **Dependencias sin uso aún:** `httpx`, `tenacity`, `python-dateutil` (reservadas para ERP/reintentos/fechas).
8. **Sin CI ni linting configurado** (no hay ruff/black/mypy, GitHub Actions, ni coverage).
