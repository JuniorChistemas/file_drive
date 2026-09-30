"""Tests de app.pipeline (helpers del pipeline)."""

from pathlib import Path

from app.pipeline import (
    diff_contracts,
    existing_compressed_path,
    filter_from_lote,
    group_by_lote,
    parse_dni_lote,
)


class TestParseDniLote:
    def test_nombre_valido(self):
        assert parse_dni_lote("73439516_A-19") == ("73439516", "A-19")

    def test_split_solo_en_el_primer_separador(self):
        assert parse_dni_lote("41453026_A2_48") == ("41453026", "A2_48")

    def test_sin_separador(self):
        assert parse_dni_lote("73439516") is None

    def test_dni_vacio(self):
        assert parse_dni_lote("_A-19") is None

    def test_lote_vacio(self):
        assert parse_dni_lote("73439516_") is None

    def test_nombre_vacio(self):
        assert parse_dni_lote("") is None


class TestGroupByLote:
    def test_agrupa_por_lote(self):
        folders = [
            {"name": "73439516_A-19", "id": "f1"},
            {"name": "03502322_A-19", "id": "f2"},
            {"name": "87565431_A-17", "id": "f3"},
        ]
        groups, invalid = group_by_lote(folders)

        assert invalid == []
        assert set(groups) == {"A-19", "A-17"}
        assert [dni for dni, _ in groups["A-19"]] == ["73439516", "03502322"]
        assert groups["A-19"][0][1]["id"] == "f1"
        assert [dni for dni, _ in groups["A-17"]] == ["87565431"]

    def test_nombres_invalidos_se_reportan_aparte(self):
        folders = [
            {"name": "73439516_A-19", "id": "f1"},
            {"name": "SINFORMATO", "id": "f2"},
        ]
        groups, invalid = group_by_lote(folders)

        assert list(groups) == ["A-19"]
        assert [f["name"] for f in invalid] == ["SINFORMATO"]

    def test_lista_vacia(self):
        assert group_by_lote([]) == ({}, [])


class TestDiffContracts:
    def test_sin_diferencias(self):
        assert diff_contracts(["1", "2"], ["2", "1"]) == ([], [])

    def test_faltantes_y_sobrantes(self):
        faltantes, sobrantes = diff_contracts(["1", "2", "3"], ["2", "4"])
        assert faltantes == ["1", "3"]
        assert sobrantes == ["4"]

    def test_resultados_ordenados(self):
        faltantes, sobrantes = diff_contracts(["9", "5"], ["8", "4"])
        assert faltantes == ["5", "9"]
        assert sobrantes == ["4", "8"]

    def test_vacios(self):
        assert diff_contracts([], []) == ([], [])


class TestFilterFromLote:
    @staticmethod
    def _groups():
        return {
            "A-10": [("11111111", {"name": "11111111_A-10", "id": "f1"})],
            "E-45": [("22222222", {"name": "22222222_E-45", "id": "f2"})],
            "F-02": [("33333333", {"name": "33333333_F-02", "id": "f3"})],
        }

    def test_vacio_devuelve_todo(self):
        groups = self._groups()
        kept, skipped = filter_from_lote(groups, "")
        assert kept == groups
        assert skipped == []

    def test_none_devuelve_todo(self):
        groups = self._groups()
        kept, skipped = filter_from_lote(groups, None)
        assert kept == groups
        assert skipped == []

    def test_filtro_inclusive(self):
        kept, skipped = filter_from_lote(self._groups(), "E-45")
        assert list(kept) == ["E-45", "F-02"]
        assert kept["E-45"][0][0] == "22222222"
        assert skipped == ["A-10"]

    def test_start_inexistente_conserva_nada(self):
        kept, skipped = filter_from_lote(self._groups(), "Z-99")
        assert kept == {}
        assert skipped == ["A-10", "E-45", "F-02"]

    def test_espacios_se_ignoran(self):
        kept, skipped = filter_from_lote(self._groups(), "  E-45  ")
        assert list(kept) == ["E-45", "F-02"]
        assert skipped == ["A-10"]

    def test_grupos_vacios(self):
        kept, skipped = filter_from_lote({}, "A-1")
        assert kept == {}
        assert skipped == []


class TestExistingCompressedPath:
    def test_existe(self, tmp_path: Path):
        compressed = tmp_path / "contrato_compressed.pdf"
        compressed.write_bytes(b"pdf")
        assert existing_compressed_path(tmp_path, "contrato.pdf") == compressed

    def test_no_existe(self, tmp_path: Path):
        assert existing_compressed_path(tmp_path, "contrato.pdf") is None

    def test_dir_destino_inexistente(self, tmp_path: Path):
        assert existing_compressed_path(tmp_path / "E-45" / "12345678", "doc.pdf") is None

    def test_ignora_original_sin_comprimir(self, tmp_path: Path):
        (tmp_path / "contrato.pdf").write_bytes(b"pdf")
        assert existing_compressed_path(tmp_path, "contrato.pdf") is None
