"""Mapeo de tipo de documento (según el nombre del PDF) a document_type_id del ERP.

Los PDFs siguen el patrón '{DNI}_{TIPO}_{LOTE}_{FECHA}...pdf'
(ej. '00371937_CONTRATO_A_16_20260722_105041.pdf'). Los tipos que no
aparecen en DOCUMENT_TYPE_IDS (p. ej. TRASPASO) se suben como OTROS.
"""

DOCUMENT_TYPE_IDS = {
    "CONTRATO": 1,
    "ADENDA": 2,
    "RESOLUCION": 3,
    "SOLICITUDDESISTIMIENTO": 5,
    "OTROS": 6,
    "PAGARE": 6,
    "ANEXOS": 7,
    "ANEXO": 7,
    "DNI": 8,
    "COMPROBANTEINICIAL": 9,
    "COMPROBANTEDEPAGO": 9,
    "SOLICITUDRESOLUCION": 10,
    "SEPARACION": 11,
    "CONTRATOPARTESEXTRAS": 12,
}

DEFAULT_DOCUMENT_TYPE_ID = DOCUMENT_TYPE_IDS["OTROS"]


def document_type_for(filename: str) -> int:
    """Devuelve el document_type_id según el nombre del archivo.

    Busca el primer token (separado por '_') que coincida con un tipo
    conocido; si no hay match se usa OTROS.
    """
    stem = filename.rsplit(".", 1)[0]
    for token in stem.upper().split("_"):
        if token in DOCUMENT_TYPE_IDS:
            return DOCUMENT_TYPE_IDS[token]
    return DEFAULT_DOCUMENT_TYPE_ID
