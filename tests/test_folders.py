"""Tests de app.drive.folders con un servicio Drive falso en memoria."""

from app.config.constants import MIME_FOLDER, MIME_PDF
from app.drive import folders


class FakeRequest:
    def __init__(self, response):
        self._response = response

    def execute(self, num_retries=0):
        return self._response


def _unescape(value: str) -> str:
    return value.replace("\\'", "'").replace("\\\\", "\\")


class FakeFiles:
    """Implementa files().list(...) con un evaluador mínimo de queries."""

    def __init__(self, files):
        self._files = files

    def list(self, q, pageSize, fields, pageToken=None):
        matched = [f for f in self._files if self._matches(f, q)]
        start = int(pageToken) if pageToken else 0
        chunk = matched[start : start + pageSize]
        response = {"files": chunk}
        if start + pageSize < len(matched):
            response["nextPageToken"] = str(start + pageSize)
        return FakeRequest(response)

    @staticmethod
    def _matches(file, query):
        for condition in query.split(" and "):
            condition = condition.strip()
            if condition == "trashed = false":
                continue
            if condition.startswith("name = "):
                expected = _unescape(condition[len("name = ") :].strip("'"))
                if file["name"] != expected:
                    return False
            elif condition.startswith("mimeType = "):
                expected = condition[len("mimeType = ") :].strip("'")
                if file["mimeType"] != expected:
                    return False
            elif condition.endswith(" in parents"):
                parent = condition[: -len(" in parents")].strip("'")
                if parent not in file.get("parents", []):
                    return False
            else:
                raise AssertionError(f"Condición no soportada por el fake: {condition}")
        return True


class FakeService:
    def __init__(self, files):
        self._files_resource = FakeFiles(files)

    def files(self):
        return self._files_resource


def _folder(fid, name, parents=None):
    return {
        "id": fid,
        "name": name,
        "mimeType": MIME_FOLDER,
        "parents": parents or [],
        "size": "0",
    }


def _pdf(fid, name, parents, size="1048576"):
    return {
        "id": fid,
        "name": name,
        "mimeType": MIME_PDF,
        "parents": parents,
        "size": size,
    }


def test_find_child_folder_sin_padre():
    service = FakeService([
        _folder("1", "MZ_A"),
        _folder("2", "OTRA"),
    ])
    found = folders.find_child_folder(service, "MZ_A")
    assert found is not None and found["id"] == "1"


def test_find_child_folder_no_existe():
    service = FakeService([_folder("1", "MZ_A")])
    assert folders.find_child_folder(service, "NO_EXISTE") is None


def test_find_child_folder_con_comilla_en_nombre():
    service = FakeService([_folder("1", "O'Brien")])
    found = folders.find_child_folder(service, "O'Brien")
    assert found is not None and found["id"] == "1"


def test_resolve_path_dos_niveles():
    service = FakeService([
        _folder("1", "MZ_A"),
        _folder("2", "0232433_A0-03", parents=["1"]),
        _folder("3", "0232433_A0-03", parents=["999"]),  # mismo nombre, otro padre
    ])
    found = folders.resolve_path(service, "MZ_A/0232433_A0-03")
    assert found is not None and found["id"] == "2"


def test_resolve_path_segmento_inexistente():
    service = FakeService([_folder("1", "MZ_A")])
    assert folders.resolve_path(service, "MZ_A/NO_EXISTE") is None


def test_find_lote_folder_ok():
    service = FakeService([
        _folder("1", "Escaneos"),
        _folder("2", "MZ_A", parents=["1"]),
        _folder("3", "7343546_A2-12", parents=["2"]),  # lote correcto
    ])
    found = folders.find_lote_folder(service, "1", "MZ_A", "7343546_A2-12")
    assert found is not None and found["id"] == "3"


def test_find_lote_folder_manzana_inexistente():
    service = FakeService([
        _folder("1", "Escaneos"),
        _folder("2", "MZ_A", parents=["1"]),
    ])
    assert folders.find_lote_folder(service, "1", "MZ_Z", "7343546_A2-12") is None


def test_find_lote_folder_lote_inexistente():
    service = FakeService([
        _folder("1", "Escaneos"),
        _folder("2", "MZ_A", parents=["1"]),
        _folder("3", "OTRO", parents=["2"]),
    ])
    assert folders.find_lote_folder(service, "1", "MZ_A", "7343546_A2-12") is None


def test_find_lote_folder_ignora_lote_en_otra_manzana():
    service = FakeService([
        _folder("1", "Escaneos"),
        _folder("2", "MZ_A", parents=["1"]),
        _folder("3", "MZ_B", parents=["1"]),
        _folder("4", "7343546_A2-12", parents=["3"]),  # bajo MZ_B, no MZ_A
    ])
    assert folders.find_lote_folder(service, "1", "MZ_A", "7343546_A2-12") is None


def test_iter_subfolders_solo_carpetas():
    service = FakeService([
        _folder("2", "SUB_A", parents=["1"]),
        _folder("3", "SUB_B", parents=["1"]),
        _pdf("4", "doc.pdf", parents=["1"]),
        _folder("5", "EXTERNA", parents=["999"]),
    ])
    names = [f["name"] for f in folders.iter_subfolders(service, "1")]
    assert names == ["SUB_A", "SUB_B"]


def test_list_pdfs_filtra_y_pagina(monkeypatch):
    monkeypatch.setattr(folders, "DRIVE_PAGE_SIZE", 2)
    service = FakeService([
        _pdf("10", "a.pdf", parents=["1"]),
        _pdf("11", "b.pdf", parents=["1"]),
        _pdf("12", "c.pdf", parents=["1"]),
        {"id": "13", "name": "img.png", "mimeType": "image/png", "parents": ["1"]},
        _pdf("14", "externo.pdf", parents=["999"]),
    ])
    pdfs = list(folders.list_pdfs(service, "1"))
    assert [p["name"] for p in pdfs] == ["a.pdf", "b.pdf", "c.pdf"]
