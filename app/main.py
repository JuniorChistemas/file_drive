"""Punto de entrada del document-worker.

Al arrancar ejecuta un smoke scan contra Drive (lista carpetas y PDFs)
y después mantiene el proceso vivo. Los workers reales (scan, process,
retry) se implementarán sobre esta base.
"""

import signal
import sys
import threading

from loguru import logger

from app.config.constants import STORAGE_TEMP_DIR
from app.drive.files import download_pdf
from app.drive.folders import find_child_folder, iter_subfolders, list_pdfs
from app.pdf.compress import compress_pdf

logger.remove()
logger.add(sys.stdout, level="INFO")
logger.add("logs/app.log", rotation="10 MB", retention="7 days", level="DEBUG")

_stop = threading.Event()


def _log_pdfs(kind: str, folder_id: str, folder_name: str, service) -> list[dict]:
    """Lista los PDFs directos de una carpeta en el log y los devuelve."""
    pdfs = list(list_pdfs(service, folder_id))
    logger.info("{} '{}': {} PDF(s)", kind, folder_name, len(pdfs))
    for pdf in pdfs:
        size = int(pdf.get("size", 0))
        logger.info("  - {} ({:.2f} MB)", pdf["name"], size / 1024 / 1024)
    return pdfs


def _handle_signal(signum, _frame):
    logger.info("Señal {} recibida, deteniendo worker...", signum)
    _stop.set()


def smoke_scan() -> None:
    """Conecta con Drive y lista los PDFs de las subcarpetas de la raíz."""
    from app.config.settings import get_settings
    from app.drive.client import build_drive_service

    # Load settings
    settings = get_settings()
    # Load service
    service = build_drive_service()

    root = find_child_folder(service, settings.drive_root_folder)
    if root is None:
        logger.error(
            "Carpeta raíz '{}' no encontrada. ¿Está compartida con la service account?",
            settings.drive_root_folder,
        )
        return

    manzana = find_child_folder(service, settings.drive_manzana_folder, root["id"])
    if manzana is None:
        logger.error(
            "Manzana '{}/{}' no encontrada.",
            settings.drive_root_folder,
            settings.drive_manzana_folder,
        )
        return

    logger.info(
        "Manzana '{}/{}' encontrada (id={})",
        root["name"],
        manzana["name"],
        manzana["id"],
    )

    lotes = list(iter_subfolders(service, manzana["id"]))
    logger.info("Carpetas de cliente (DNI_LOTE): {}", len(lotes))
    total = 0
    ok = 0
    for lote in lotes:
        pdfs = _log_pdfs("lote", lote["id"], lote["name"], service)
        for pdf in pdfs:
            total += 1
            if _process_pdf(service, pdf, lote["name"]):
                ok += 1
    logger.info("Procesamiento completado: {}/{} PDF(s) comprimidos", ok, total)


def _process_pdf(service, pdf: dict, lote_name: str) -> bool:
    """Descarga y comprime un PDF de Drive a STORAGE_TEMP_DIR.

    Devuelve True si terminó OK, False si falló. Ante cualquier error se
    loguea y se continúa con el siguiente archivo sin romper el batch.

    VERIFICAR EL ORDEN
    """
    name = pdf.get("name", "sin_nombre")
    try:
        local_path = download_pdf(service, pdf, STORAGE_TEMP_DIR)
        compressed = compress_pdf(local_path)
        logger.info("[{}] OK {} -> {}", lote_name, name, compressed.name)
        return True
    except Exception as exc:
        logger.exception("[{}] FALLÓ '{}': {}", lote_name, name, exc)
        return False


def main() -> None:

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info("document-worker iniciado, empieza proceso de carga de archivos")
    try:
        smoke_scan()
    except Exception:
        logger.exception("Smoke scan falló; el worker seguirá vivo")

    while not _stop.wait(timeout=30):
        logger.debug("worker en espera...")

    logger.info("document-worker detenido")


if __name__ == "__main__":
    main()
