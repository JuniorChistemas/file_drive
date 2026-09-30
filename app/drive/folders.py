"""Navegación y listado de carpetas/archivos en Google Drive."""

from collections.abc import Iterator
from typing import Any

from app.config.constants import (
    DRIVE_FILE_FIELDS,
    DRIVE_NUM_RETRIES,
    DRIVE_PAGE_SIZE,
    MIME_FOLDER,
    MIME_PDF,
)


def _escape(value: str) -> str:
    """Escapa comillas simples para las queries de Drive API."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _list_all(service: Any, query: str) -> Iterator[dict]:
    """Itera todos los resultados de una query manejando la paginación.

    execute(num_retries=...) reintenta con backoff los errores transitorios
    de Drive (500/502/503/429); los 4xx se lanzan sin reintentar.
    """
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
            .execute(num_retries=DRIVE_NUM_RETRIES)
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
    """Resuelve una ruta tipo 'Escaneos/Manzana G/7343546_A2-12' segmento a segmento.
    Devuelve el dict de la carpeta final o None si algún segmento no existe.
    """
    current = None
    for segment in [s for s in path.strip("/").split("/") if s]:
        parent_id = current["id"] if current else None
        current = find_child_folder(service, segment, parent_id)
        if current is None:
            return None
    return current


def find_lote_folder(service: Any, root_id: str, manzana: str, dni_lote: str) -> dict | None:
    """Resuelve la carpeta del cliente bajo la jerarquía fija
    Escaneos/(manzana)/(DNI_LOTE).

    - root_id: id de la carpeta raíz 'Escaneos' (settings.drive_root_folder).
    - manzana: nombre de la manzana, ej. 'MZ_A' (settings.drive_manzana_folder).
    - dni_lote: nombre de la carpeta del cliente, ej. '7343546_A2-12'.

    Devuelve el dict de la carpeta DNI_LOTE o None si la manzana o el lote
    no existen.
    """
    manzana_folder = find_child_folder(service, manzana, root_id)
    if manzana_folder is None:
        return None
    return find_child_folder(service, dni_lote, manzana_folder["id"])


def iter_subfolders(service: Any, folder_id: str) -> Iterator[dict]:
    """Itera las subcarpetas directas de una carpeta."""
    query = f"'{folder_id}' in parents and mimeType = '{MIME_FOLDER}' and trashed = false"
    yield from _list_all(service, query)


def list_pdfs(service: Any, folder_id: str) -> Iterator[dict]:
    """Itera los PDFs directos de una carpeta."""
    query = f"'{folder_id}' in parents and mimeType = '{MIME_PDF}' and trashed = false"
    yield from _list_all(service, query)
