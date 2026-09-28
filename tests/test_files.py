"""Tests de app.drive.files con un servicio Drive falso en memoria."""

from pathlib import Path

import pytest

from app.config.constants import MIME_PDF
from app.drive import files


class FakeGetMediaRequest:
    """Request devuelto por files().get_media(); el downloader lee de él."""

    def __init__(self, payload: bytes):
        self._payload = payload

    def execute(self):
        return self._payload


class FakeFilesResource:
    def __init__(self, payloads: dict[str, bytes]):
        self._payloads = payloads

    def get_media(self, fileId):
        return FakeGetMediaRequest(self._payloads[fileId])


class FakeFiles:
    def __init__(self, payloads):
        self._resource = FakeFilesResource(payloads)

    def get_media(self, fileId):
        return self._resource.get_media(fileId)


class FakeService:
    def __init__(self, payloads: dict[str, bytes]):
        self._files = FakeFiles(payloads)

    def files(self):
        return self._files


class _FakeDownloader:
    """Sustituye a MediaIoBaseDownload: escribe el payload en una pasada."""

    def __init__(self, fh, request, chunksize=None):
        self._fh = fh
        self._payload = request.execute()

    def next_chunk(self):
        self._fh.write(self._payload)
        return None, True


@pytest.fixture(autouse=True)
def _patch_downloader(monkeypatch):
    monkeypatch.setattr(files, "MediaIoBaseDownload", _FakeDownloader)


def test_download_file_writes_bytes(tmp_path: Path):
    payload = b"%PDF-1.4\n%%EOF"
    service = FakeService({"file-1": payload})
    file = {"id": "file-1", "name": "doc.pdf", "mimeType": MIME_PDF}

    path = files.download_file(service, file, tmp_path)

    assert path == tmp_path / "doc.pdf"
    assert path.read_bytes() == payload


def test_download_file_creates_dest_dir(tmp_path: Path):
    nested = tmp_path / "deep" / "sub"
    service = FakeService({"file-2": b"data"})
    file = {"id": "file-2", "name": "x.pdf", "mimeType": MIME_PDF}

    path = files.download_file(service, file, nested)
    assert path == nested / "x.pdf"
    assert nested.exists()
    assert path.read_bytes() == b"data"


def test_download_pdf_validates_mimetype(tmp_path: Path):
    service = FakeService({"file-3": b"data"})
    bad = {"id": "file-3", "name": "img.png", "mimeType": "image/png"}
    with pytest.raises(ValueError, match="no es un PDF"):
        files.download_pdf(service, bad, tmp_path)


def test_download_pdf_ok(tmp_path: Path):
    pdf_bytes = b"%PDF-1.4\n%%EOF"
    service = FakeService({"file-4": pdf_bytes})
    pdf = {"id": "file-4", "name": "ok.pdf", "mimeType": MIME_PDF}

    path = files.download_pdf(service, pdf, tmp_path)
    assert path.read_bytes() == pdf_bytes