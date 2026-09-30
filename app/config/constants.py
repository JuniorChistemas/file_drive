"""Constantes del proyecto."""

from pathlib import Path

# Google Drive API
# Nota: cuando se implementen upload/move, ampliar a
# "https://www.googleapis.com/auth/drive"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
DRIVE_PAGE_SIZE = 1000
# Reintentos con backoff para errores transitorios de Drive (5xx, 429)
DRIVE_NUM_RETRIES = 3
DRIVE_FILE_FIELDS = "nextPageToken, files(id, name, mimeType, size, modifiedTime, parents)"

# MIME types
MIME_FOLDER = "application/vnd.google-apps.folder"
MIME_PDF = "application/pdf"

# Storage layout (relativo al paquete app/)
_APP_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = _APP_DIR / "storage"
STORAGE_TEMP_DIR = STORAGE_DIR / "temp"
STORAGE_PROCESSED_DIR = STORAGE_DIR / "processed"
STORAGE_FAILED_DIR = STORAGE_DIR / "failed"
STORAGE_DUPLICATED_DIR = STORAGE_DIR / "duplicated"

# ERP
# El backend procesa cada archivo de forma SÍNCRONA en el POST de subida:
# la respuesta solo llega cuando termina el procesamiento, por eso la subida
# usa un timeout mucho más largo que el resto de endpoints.
ERP_REQUEST_TIMEOUT = 30.0  # s: login, consulta de lote, lot-assignments
ERP_UPLOAD_TIMEOUT = 300.0  # s (5 min): subida de assignment-documents

# Ghostscript
GS_BINARY = "gs"
GS_COMPATIBILITY = "1.4"
GS_PDF_PROFILE = "/ebook"  # 150 dpi, calidad media apropiada para escaneos
