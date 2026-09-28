"""Tests de app.pdf.compress.

Requieren el binario `gs` (instalado en el contenedor, ver Dockerfile) y
PyMuPDF para generar un PDF de fixture en runtime.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

import fitz

from app.config.constants import STORAGE_TEMP_DIR
from app.pdf import compress


GS_AVAILABLE = shutil.which("gs") is not None


def _make_pdf(path: Path, pages: int = 1) -> Path:
    """Crea un PDF válido en path usando PyMuPDF."""
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page(width=595, height=842)  # A4
        page.insert_text((72, 100), "fixture de prueba para compresion",
                         fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def fixture_pdf(tmp_path: Path) -> Path:
    return _make_pdf(tmp_path / "sample.pdf")


def _gs_sleep():
    """Marca de skip si Ghostscript no está disponible en el sistema."""
    return pytest.mark.skipif(
        not GS_AVAILABLE, reason="Ghostscript no instalado"
    )


@_gs_sleep()
def test_compress_pdf_creates_output(fixture_pdf: Path):
    out = compress.compress_pdf(fixture_pdf)

    assert out.exists()
    assert out.suffix == ".pdf"
    assert out.stem == "sample_compressed"


@_gs_sleep()
def test_compress_pdf_output_is_valid_pdf(fixture_pdf: Path):
    out = compress.compress_pdf(fixture_pdf)

    with fitz.open(str(out)) as doc:
        assert doc.page_count >= 1
        assert doc.is_pdf


@_gs_sleep()
def test_compress_pdf_uses_given_output_dir(fixture_pdf: Path, tmp_path: Path):
    custom = tmp_path / "custom_out"
    out = compress.compress_pdf(fixture_pdf, output_dir=custom)

    assert out.parent == custom
    assert custom.exists()


@_gs_sleep()
def test_compress_pdf_writes_into_storage_temp(fixture_pdf: Path):
    # output_dir por defecto = STORAGE_TEMP_DIR
    out = compress.compress_pdf(fixture_pdf)

    assert out.parent == STORAGE_TEMP_DIR
    out.unlink(missing_ok=True)


def test_compress_pdf_raises_on_missing_input(tmp_path: Path):
    with pytest.raises(compress.CompressError, match="no existe"):
        compress.compress_pdf(tmp_path / "missing.pdf")


def test_compress_pdf_raises_on_non_pdf(tmp_path: Path):
    txt = tmp_path / "not_a_pdf.txt"
    txt.write_text("hola")
    with pytest.raises(compress.CompressError, match="no es un PDF"):
        compress.compress_pdf(txt)


@_gs_sleep()
def test_compress_pdf_raises_when_gs_fails(monkeypatch, fixture_pdf: Path):
    def _bad_run(*a, **kw):
        return subprocess.CompletedProcess(
            a[0], returncode=1, stdout="", stderr="boom"
        )

    monkeypatch.setattr(compress.subprocess, "run", _bad_run)
    with pytest.raises(compress.CompressError, match="boom"):
        compress.compress_pdf(fixture_pdf)


@_gs_sleep()
def test_compress_pdf_raises_when_gs_not_found(monkeypatch, fixture_pdf: Path):
    def _not_found(*a, **kw):
        raise FileNotFoundError("gs")

    monkeypatch.setattr(compress.subprocess, "run", _not_found)
    with pytest.raises(compress.CompressError, match="no encontrado"):
        compress.compress_pdf(fixture_pdf)