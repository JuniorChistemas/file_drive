"""Descarga de archivos desde Google Drive."""

from pathlib import Path
from typing import Any

from googleapiclient.http import MediaIoBaseDownload

from app.config.constants import DRIVE_NUM_RETRIES, MIME_PDF


def download_file(service: Any, file: dict, dest_dir: Path) -> Path:
    """Descarga un archivo de Drive a dest_dir vía streaming.

    - file: dict con 'id' y 'name' (el retornado por list_pdfs).
    - dest_dir: carpeta destino (se crea si no existe).
    Devuelve la ruta del archivo descargado.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / file["name"]

    request = service.files().get_media(fileId=file["id"])
    with open(dest_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=1024 * 1024)
        done = False
        while not done:
            # num_retries reintenta con backoff los errores transitorios (5xx, 429)
            _status, done = downloader.next_chunk(num_retries=DRIVE_NUM_RETRIES)

    return dest_path


def download_pdf(service: Any, file: dict, dest_dir: Path) -> Path:
    """Descarga un PDF de Drive validando su mimeType.

    - file: dict con 'id', 'name' y 'mimeType'.
    Lanza ValueError si el archivo no es un PDF.
    """
    if file.get("mimeType") != MIME_PDF:
        raise ValueError(
            f"El archivo '{file.get('name')}' no es un PDF "
            f"(mimeType={file.get('mimeType')!r})"
        )
    return download_file(service, file, dest_dir)