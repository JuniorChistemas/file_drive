"""Punto de entrada del document-worker.

Pipeline al arrancar:
1. Login ERP (bearer token vía /api/auth/login).
2. Scan Drive: raíz → manzana → carpetas DNI_LOTE, agrupadas por LOTE.
3. Por cada LOTE: descarga + compresión en storage/temp/{LOTE}/{DNI}/,
   consulta ERP por lote (warnings si faltan o sobran contratos),
   creación de lot_assignments y subida de documentos comprimidos.
4. Resumen final (contratos subidos/omitidos) y proceso en espera.

La subida de documentos es SÍNCRONA: cada POST espera a que el backend
termine de procesar el archivo (timeout de 5 min) antes de continuar con
el siguiente documento/carpeta; al agotarse el timeout: warning + continue.
"""

import signal
import sys
import threading
from pathlib import Path

from loguru import logger

from app.config.constants import STORAGE_TEMP_DIR
from app.drive.files import download_pdf
from app.drive.folders import find_child_folder, iter_subfolders, list_pdfs
from app.erp.client import ErpClient, ErpError, login
from app.erp.doctypes import document_type_for
from app.pdf.compress import compress_pdf
from app.pipeline import (
    diff_contracts,
    existing_compressed_path,
    filter_from_lote,
    group_by_lote,
)

logger.remove()
logger.add(sys.stdout, level="INFO")
logger.add("logs/app.log", rotation="10 MB", retention="7 days", level="DEBUG")

_stop = threading.Event()


def _handle_signal(signum, _frame):
    logger.info("Señal {} recibida, deteniendo worker...", signum)
    _stop.set()


def _resolve_manzana(service, settings) -> dict | None:
    """Resuelve raíz → manzana en Drive. Devuelve la carpeta manzana o None."""
    root = find_child_folder(service, settings.drive_root_folder)
    if root is None:
        logger.error(
            "Carpeta raíz '{}' no encontrada. ¿Está compartida con la service account?",
            settings.drive_root_folder,
        )
        return None

    manzana = find_child_folder(service, settings.drive_manzana_folder, root["id"])
    if manzana is None:
        logger.error(
            "Manzana '{}/{}' no encontrada.",
            settings.drive_root_folder,
            settings.drive_manzana_folder,
        )
        return None

    logger.info(
        "Manzana '{}/{}' encontrada (id={})",
        root["name"],
        manzana["name"],
        manzana["id"],
    )
    return manzana


def _erp_login(settings) -> ErpClient | None:
    """Autentica contra el ERP. Devuelve None si no se puede (solo local)."""
    if not settings.erp_api_url:
        logger.warning("ERP_API_URL no configurada; se procesa local sin subir al ERP")
        return None
    try:
        token = login(settings.erp_api_url, settings.erp_username, settings.erp_password)
    except ErpError as exc:
        logger.error("{}; se procesa local sin subir al ERP", exc)
        return None
    logger.info("Login ERP exitoso ({})", settings.erp_api_url)
    return ErpClient(settings.erp_api_url, token, api_key=settings.erp_api_key)


def _download_and_compress(service, pdf: dict, lote: str, dni: str) -> Path | None:
    """Descarga y comprime un PDF a storage/temp/{LOTE}/{DNI}/.

    Si el comprimido ya existe (corrida anterior interrumpida), se reutiliza
    sin re-descargar ni re-comprimir.

    Devuelve la ruta del comprimido o None si falló (se loguea y se
    continúa con el siguiente archivo sin romper el batch).
    """
    name = pdf.get("name", "sin_nombre")
    dest_dir = STORAGE_TEMP_DIR / lote / dni
    reused = existing_compressed_path(dest_dir, name)
    if reused is not None:
        logger.info("[{}] DNI {}: '{}' ya comprimido; se reutiliza", lote, dni, name)
        return reused
    try:
        local_path = download_pdf(service, pdf, dest_dir)
        return compress_pdf(local_path, output_dir=dest_dir)
    except Exception as exc:
        logger.exception("[{}] {} FALLÓ '{}': {}", lote, dni, name, exc)
        return None


def _upload_contract(
    erp: ErpClient,
    lote: str,
    dni: str,
    customer_id: int,
    lot_id: int,
    files: list[Path],
    stats: dict,
) -> None:
    """Crea el lot_assignment del contrato y sube sus PDFs comprimidos.

    Cada subida es síncrona: espera (hasta ERP_UPLOAD_TIMEOUT) a que el
    backend termine de procesar el archivo antes de continuar con el
    siguiente documento del contrato.
    """
    try:
        assignment_id = erp.create_lot_assignment(customer_id, lot_id)
    except ErpError as exc:
        logger.warning("[{}] DNI {}: {}; se omite el contrato", lote, dni, exc)
        stats["omitted"] += 1
        return

    logger.info("[{}] DNI {}: lot_assignment creado (id={})", lote, dni, assignment_id)
    stats["uploaded"] += 1

    for path in files:
        doc_type = document_type_for(path.name)
        try:
            erp.upload_document(assignment_id, doc_type, path)
        except ErpError as exc:
            logger.warning("[{}] DNI {}: {}", lote, dni, exc)
            stats["docs_failed"] += 1
            continue
        logger.info(
            "[{}] DNI {}: '{}' subido (document_type_id={})",
            lote,
            dni,
            path.name,
            doc_type,
        )
        stats["docs_ok"] += 1


def _process_lote(service, erp: ErpClient | None, lote: str, entries: list, stats: dict) -> None:
    """Procesa un LOTE: descarga+compresión local y subida al ERP."""
    logger.info("=== Lote '{}': {} carpeta(s) ===", lote, len(entries))

    # Fase local: descargar + comprimir en storage/temp/{LOTE}/{DNI}/
    # El listado de una carpeta puede fallar (p. ej. 500 transitorio de
    # Drive agotando los reintentos); se aísla por carpeta para no perder
    # el resto del lote.
    local: dict[str, list[Path]] = {}
    for dni, folder in entries:
        try:
            pdfs = list(list_pdfs(service, folder["id"]))
        except Exception:
            logger.exception(
                "[{}] DNI {}: FALLÓ el listado de '{}'; se omite la carpeta",
                lote,
                dni,
                folder.get("name"),
            )
            continue
        logger.info("[{}] '{}': {} PDF(s)", lote, folder["name"], len(pdfs))
        for pdf in pdfs:
            compressed = _download_and_compress(service, pdf, lote, dni)
            if compressed is not None:
                local.setdefault(dni, []).append(compressed)

    if erp is None:
        return

    # Fase ERP: consulta por lote y diff de contratos
    try:
        payload = erp.get_lot_contracts(lote)
    except ErpError as exc:
        logger.warning("[{}] {}; se omite la subida del lote", lote, exc)
        stats["omitted"] += len(local)
        return

    data = payload.get("data") or {}
    lot_id = data.get("lot_id")
    if lot_id is None:
        logger.warning("[{}] La respuesta del ERP no trae lot_id; se omite la subida", lote)
        stats["omitted"] += len(local)
        return

    contracts: list[tuple[str, int]] = []
    for raw in data.get("contracts") or []:
        customer = raw.get("customer") or {}
        dni = customer.get("document_number")
        customer_id = customer.get("customer_id")
        if not dni or customer_id is None:
            logger.warning(
                "[{}] Contrato {} sin DNI/customer_id; se omite",
                lote,
                raw.get("correlative"),
            )
            stats["omitted"] += 1
            continue
        contracts.append((dni, customer_id))

    faltantes, sobrantes = diff_contracts((dni for dni, _ in contracts), local.keys())
    for dni in faltantes:
        logger.warning(
            "[{}] FALTA: el DNI {} tiene contrato en el ERP pero no hay carpeta en Drive",
            lote,
            dni,
        )
    for dni in sobrantes:
        logger.warning(
            "[{}] SOBRA: la carpeta del DNI {} no tiene contrato en el ERP; no se sube",
            lote,
            dni,
        )
    stats["omitted"] += len(faltantes) + len(sobrantes)

    # Subida: un lot_assignment por contrato con carpeta local
    for dni, customer_id in contracts:
        files = local.get(dni)
        if not files:
            continue  # ya logueado como FALTA en el diff
        _upload_contract(erp, lote, dni, customer_id, lot_id, files, stats)


def run_pipeline() -> None:
    """Ejecuta el pipeline completo: Drive → compresión → ERP."""
    from app.config.settings import get_settings
    from app.drive.client import build_drive_service

    settings = get_settings()
    service = build_drive_service()

    manzana = _resolve_manzana(service, settings)
    if manzana is None:
        return

    folders = list(iter_subfolders(service, manzana["id"]))
    groups, invalid = group_by_lote(folders)
    for folder in invalid:
        logger.warning(
            "Carpeta '{}' no cumple el formato DNI_LOTE; se omite", folder.get("name")
        )
    if settings.pipeline_start_from_lote:
        groups, skipped_lotes = filter_from_lote(groups, settings.pipeline_start_from_lote)
        if skipped_lotes:
            logger.info(
                "Reanudación: {} lote(s) anteriores a '{}' saltados: {}",
                len(skipped_lotes),
                settings.pipeline_start_from_lote,
                ", ".join(skipped_lotes),
            )
    logger.info(
        "Carpetas DNI_LOTE a procesar: {} ({} lote(s))",
        sum(len(v) for v in groups.values()),
        len(groups),
    )

    erp = _erp_login(settings)
    stats = {"uploaded": 0, "omitted": 0, "docs_ok": 0, "docs_failed": 0}
    failed_lotes: list[str] = []
    try:
        for lote, entries in sorted(groups.items()):
            try:
                _process_lote(service, erp, lote, entries, stats)
            except Exception:
                logger.exception(
                    "Lote '{}' falló de forma inesperada; se continúa con el siguiente",
                    lote,
                )
                failed_lotes.append(lote)
    finally:
        if erp is not None:
            erp.close()

    logger.info(
        "Resultado final: {} contrato(s) subidos, {} omitido(s); "
        "{} documento(s) subidos, {} fallido(s)",
        stats["uploaded"],
        stats["omitted"],
        stats["docs_ok"],
        stats["docs_failed"],
    )
    if failed_lotes:
        logger.warning(
            "Lotes fallidos: {}. Antes de reprocesarlos, verificar en logs qué "
            "contratos ya se subieron (el ERP no deduplica lot_assignments)",
            ", ".join(failed_lotes),
        )


def main() -> None:

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info("document-worker iniciado, empieza proceso de carga de archivos")
    try:
        run_pipeline()
    except Exception:
        logger.exception("Pipeline falló; el worker seguirá vivo")

    while not _stop.wait(timeout=30):
        logger.debug("worker en espera...")

    logger.info("document-worker detenido")


if __name__ == "__main__":
    main()
