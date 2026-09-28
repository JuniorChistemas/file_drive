"""Constantes del proyecto."""

from pathlib import Path

# Google Drive API
# Nota: cuando se implementen upload/move, ampliar a
# "https://www.googleapis.com/auth/drive"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
DRIVE_PAGE_SIZE = 1000
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

# Ghostscript
GS_BINARY = "gs"
GS_COMPATIBILITY = "1.4"
GS_PDF_PROFILE = "/ebook"  # 150 dpi, calidad media apropiada para escaneos
