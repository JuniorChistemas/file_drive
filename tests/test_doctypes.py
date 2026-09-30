"""Tests de app.erp.doctypes (filename → document_type_id)."""

from app.erp.doctypes import DOCUMENT_TYPE_IDS, document_type_for


def test_contrato():
    assert (
        document_type_for("00371937_CONTRATO_A_16_20260722_105041.pdf")
        == DOCUMENT_TYPE_IDS["CONTRATO"]
    )


def test_separacion():
    assert (
        document_type_for("16780155_SEPARACION_A_32_20260722_115410.pdf")
        == DOCUMENT_TYPE_IDS["SEPARACION"]
    )


def test_dni():
    assert document_type_for("73439516_DNI_A-19_20260722.pdf") == DOCUMENT_TYPE_IDS["DNI"]


def test_pagare():
    assert document_type_for("73439516_PAGARE_A-19.pdf") == DOCUMENT_TYPE_IDS["PAGARE"]


def test_anexos():
    assert document_type_for("73439516_ANEXOS_A-19.pdf") == DOCUMENT_TYPE_IDS["ANEXOS"]


def test_comprobante_inicial():
    assert (
        document_type_for("73439516_COMPROBANTEINICIAL_A-19.pdf")
        == DOCUMENT_TYPE_IDS["COMPROBANTEINICIAL"]
    )


def test_comprobante_de_pago():
    assert (
        document_type_for("73439516_COMPROBANTEDEPAGO_A-19.pdf")
        == DOCUMENT_TYPE_IDS["COMPROBANTEDEPAGO"]
    )


def test_comprimido_mantiene_el_tipo():
    assert (
        document_type_for("00371937_CONTRATO_A_16_20260722_105041_compressed.pdf")
        == DOCUMENT_TYPE_IDS["CONTRATO"]
    )


def test_tipos_con_id_propio():
    assert (
        document_type_for("02830821_ADENDA_A_59_20260916_090520.pdf")
        == DOCUMENT_TYPE_IDS["ADENDA"]
    )
    assert document_type_for("73439516_RESOLUCION_A-19.pdf") == DOCUMENT_TYPE_IDS["RESOLUCION"]
    assert (
        document_type_for("73439516_SOLICITUDDESISTIMIENTO_A-19.pdf")
        == DOCUMENT_TYPE_IDS["SOLICITUDDESISTIMIENTO"]
    )
    assert (
        document_type_for("73439516_SOLICITUDRESOLUCION_A-19.pdf")
        == DOCUMENT_TYPE_IDS["SOLICITUDRESOLUCION"]
    )
    assert (
        document_type_for("73439516_CONTRATOPARTESEXTRAS_A-19.pdf")
        == DOCUMENT_TYPE_IDS["CONTRATOPARTESEXTRAS"]
    )


def test_tipos_desconocidos_caen_en_otros():
    assert (
        document_type_for("46446652_TRASPASO_A_23_20260722_114644.pdf")
        == DOCUMENT_TYPE_IDS["OTROS"]
    )


def test_minusculas():
    assert document_type_for("73439516_contrato_A-19.pdf") == DOCUMENT_TYPE_IDS["CONTRATO"]


def test_sin_match_en_ningun_token():
    assert document_type_for("archivo.pdf") == DOCUMENT_TYPE_IDS["OTROS"]
