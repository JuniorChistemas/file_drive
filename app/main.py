"""Punto de entrada del document-worker.

Al arrancar ejecuta un smoke scan contra Drive (lista carpetas y PDFs)
y después mantiene el proceso vivo. Los workers reales (scan, process,
retry) se implementarán sobre esta base.
"""

import signal
import sys
import threading

from loguru import logger

from app.drive.folders import find_child_folder, iter_subfolders, list_pdfs

logger.remove()
logger.add(sys.stdout, level="INFO")
logger.add("logs/app.log", rotation="10 MB", retention="7 days", level="DEBUG")

_stop = threading.Event()


def _log_pdfs(kind: str, folder_id: str, folder_name: str, service) -> None:
    """Lista los PDFs directos de una carpeta en el log."""
    pdfs = list(list_pdfs(service, folder_id))
    logger.info("{} '{}': {} PDF(s)", kind, folder_name, len(pdfs))
    for pdf in pdfs:
        size = int(pdf.get("size", 0))
        logger.info("  - {} ({:.2f} MB)", pdf["name"], size / 1024 / 1024)


def _handle_signal(signum, _frame):
    logger.info("Señal {} recibida, deteniendo worker...", signum)
    _stop.set()


def smoke_scan() -> None:
    """Conecta con Drive y lista los PDFs de las subcarpetas de la raíz."""
    from app.config.settings import get_settings
    from app.drive.client import build_drive_service

    # Load settings
    settings = get_settings()
    
    service = build_drive_service()

    root = find_child_folder(service, settings.drive_root_folder)
    if root is None:
        logger.error(
            "Carpeta raíz '{}' no encontrada. ¿Está compartida con la service account?",
            settings.drive_root_folder,
        )
        return

    logger.info("Carpeta raíz '{}' encontrada (id={})", root["name"], root["id"])

    subfolders = list(iter_subfolders(service, root["id"]))
    logger.info("Subcarpetas de la raíz: {}", len(subfolders))
    for subfolder in subfolders:
        _log_pdfs("subcarpeta", subfolder["id"], subfolder["name"], service)


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info("document-worker iniciado")
    try:
        smoke_scan()
    except Exception:
        logger.exception("Smoke scan falló; el worker seguirá vivo")

    while not _stop.wait(timeout=30):
        logger.debug("worker en espera...")

    logger.info("document-worker detenido")


if __name__ == "__main__":
    main()
