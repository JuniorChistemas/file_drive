"""Navegación y listado de carpetas/archivos en Google Drive."""

from collections.abc import Iterator
from typing import Any

from app.config.constants import (
    DRIVE_FILE_FIELDS,
    DRIVE_PAGE_SIZE,
    MIME_FOLDER,
    MIME_PDF,
)


def _escape(value: str) -> str:
    """Escapa comillas simples para las queries de Drive API."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _list_all(service: Any, query: str) -> Iterator[dict]:
    """Itera todos los resultados de una query manejando la paginación."""
    page_token = None
    while True:
        response = (
            service.files()
            .list(
                q=query,
                pageSize=DRIVE_PAGE_SIZE,
                fields=DRIVE_FILE_FIELDS,
                pageToken=page_token,
            )
            .execute()
        )
        yield from response.get("files", [])
        page_token = response.get("nextPageToken")
        if not page_token:
            break


def find_child_folder(service: Any, name: str, parent_id: str | None = None) -> dict | None:
    """Busca una carpeta por nombre. Sin parent_id busca en todo el Drive visible."""
    conditions = [
        f"name = '{_escape(name)}'",
        f"mimeType = '{MIME_FOLDER}'",
        "trashed = false",
    ]
    if parent_id:
        conditions.append(f"'{parent_id}' in parents")
    return next(_list_all(service, " and ".join(conditions)), None)


def resolve_path(service: Any, path: str) -> dict | None:
    """Resuelve una ruta tipo 'MZ_A/0232433_A0-03' segmento a segmento.
    Devuelve el dict de la carpeta final o None si algún segmento no existe.
    """
    current = None
    for segment in [s for s in path.strip("/").split("/") if s]:
        parent_id = current["id"] if current else None
        current = find_child_folder(service, segment, parent_id)
        if current is None:
            return None
    return current


def iter_subfolders(service: Any, folder_id: str) -> Iterator[dict]:
    """Itera las subcarpetas directas de una carpeta."""
    query = f"'{folder_id}' in parents and mimeType = '{MIME_FOLDER}' and trashed = false"
    yield from _list_all(service, query)


def list_pdfs(service: Any, folder_id: str) -> Iterator[dict]:
    """Itera los PDFs directos de una carpeta."""
    query = f"'{folder_id}' in parents and mimeType = '{MIME_PDF}' and trashed = false"
    yield from _list_all(service, query)
