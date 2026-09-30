"""Helpers del pipeline de procesamiento (testeables, sin red ni APIs externas)."""

from collections.abc import Iterable
from pathlib import Path


def parse_dni_lote(folder_name: str) -> tuple[str, str] | None:
    """Divide un nombre de carpeta 'DNI_LOTE' (ej. '73439516_A-19').

    El split se hace en el primer '_' (el DNI no contiene '_'; el lote
    puede contener '-' u otros caracteres). Devuelve (dni, lote) o None
    si el nombre no cumple el formato.
    """
    dni, sep, lote = folder_name.partition("_")
    if not sep or not dni or not lote:
        return None
    return dni, lote


def group_by_lote(
    folders: Iterable[dict],
) -> tuple[dict[str, list[tuple[str, dict]]], list[dict]]:
    """Agrupa carpetas DNI_LOTE por LOTE.

    - folders: dicts de Drive con al menos 'name'.
    Devuelve (grupos, inválidas):
    - grupos: {lote: [(dni, folder), ...]}
    - inválidas: carpetas cuyo nombre no cumple el formato DNI_LOTE.
    """
    groups: dict[str, list[tuple[str, dict]]] = {}
    invalid: list[dict] = []
    for folder in folders:
        parsed = parse_dni_lote(folder.get("name", ""))
        if parsed is None:
            invalid.append(folder)
            continue
        dni, lote = parsed
        groups.setdefault(lote, []).append((dni, folder))
    return groups, invalid


def filter_from_lote(
    groups: dict[str, list[tuple[str, dict]]],
    start_from: str | None,
) -> tuple[dict[str, list[tuple[str, dict]]], list[str]]:
    """Filtra grupos de lotes para reanudar una corrida interrumpida.

    Conserva solo los lotes >= start_from (comparación lexicográfica, el
    mismo orden con el que run_pipeline procesa los lotes). Evita
    reprocesar lotes ya subidos al ERP, que duplicaría sus lot_assignments.

    - start_from: lote desde el cual procesar (inclusive); None/vacío
      devuelve los grupos sin filtrar.
    Devuelve (grupos_filtrados, lotes_saltados_ordenados).
    """
    start = (start_from or "").strip()
    if not start:
        return groups, []
    kept = {lote: entries for lote, entries in groups.items() if lote >= start}
    skipped = sorted(lote for lote in groups if lote < start)
    return kept, skipped


def existing_compressed_path(dest_dir: Path, pdf_name: str) -> Path | None:
    """Devuelve la ruta del comprimido de un PDF si ya existe en dest_dir.

    El comprimido de 'contrato.pdf' es 'contrato_compressed.pdf' (el mismo
    nombre que genera compress_pdf). Devuelve None si no existe, para que
    el caller lo descargue y comprima de nuevo. Permite reutilizar el
    trabajo local de una corrida anterior interrumpida.
    """
    compressed = dest_dir / f"{Path(pdf_name).stem}_compressed.pdf"
    return compressed if compressed.exists() else None


def diff_contracts(
    erp_dnis: Iterable[str], local_dnis: Iterable[str]
) -> tuple[list[str], list[str]]:
    """Compara los DNIs reportados por el ERP contra las carpetas locales.

    Devuelve (faltantes, sobrantes), ambos ordenados:
    - faltantes: DNIs que el ERP reporta pero no tienen carpeta en Drive.
    - sobrantes: carpetas en Drive que el ERP no reporta para el lote.
    """
    erp_set = set(erp_dnis)
    local_set = set(local_dnis)
    return sorted(erp_set - local_set), sorted(local_set - erp_set)
