"""Compresión de PDFs con Ghostscript.

El binario `gs` se instala en el contenedor (ver Dockerfile).
La función opera exclusivamente con paths locales; el caller se encarga
de descargar el PDF de Drive o recibirlo por HTTP (endpoint pendiente).
"""

import subprocess
from pathlib import Path

from loguru import logger

from app.config.constants import (
    GS_BINARY,
    GS_COMPATIBILITY,
    GS_PDF_PROFILE,
    STORAGE_TEMP_DIR,
)


class CompressError(RuntimeError):
    """Fallo durante la compresión con Ghostscript."""


def compress_pdf(input_path: Path, output_dir: Path | None = None) -> Path:
    """Comprime un PDF con Ghostscript y guarda el resultado en temp.

    - input_path: ruta del PDF original (debe existir y terminar en .pdf).
    - output_dir: carpeta destino; por defecto STORAGE_TEMP_DIR.
    Devuelve la ruta del PDF comprimido.

    Lanza CompressError (RuntimeError) si la entrada no es un PDF válido,
    si `gs` falla o si no se genera el archivo de salida.
    """
    if not isinstance(input_path, Path):
        input_path = Path(input_path)
    if not input_path.exists():
        raise CompressError(f"Entrada no existe: {input_path}")
    if input_path.suffix.lower() != ".pdf":
        raise CompressError(f"La entrada no es un PDF: {input_path}")

    out_dir = output_dir or STORAGE_TEMP_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"{input_path.stem}_compressed.pdf"

    cmd = [
        GS_BINARY,
        f"-dCompatibilityLevel={GS_COMPATIBILITY}",
        f"-dPDFSETTINGS={GS_PDF_PROFILE}",
        "-dNOPAUSE",
        "-dBATCH",
        "-dQUIET",
        "-sDEVICE=pdfwrite",
        f"-sOutputFile={output_path}",
        str(input_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise CompressError(
            f"Ghostscript ('{GS_BINARY}') no encontrado. ¿Está instalado?"
        ) from exc

    if result.returncode != 0 or not output_path.exists():
        raise CompressError(
            f"Ghostscript falló (code={result.returncode}): {result.stderr.strip()}"
        )

    in_size = input_path.stat().st_size
    out_size = output_path.stat().st_size
    ratio = (1 - out_size / in_size) * 100 if in_size else 0.0
    logger.info(
        "PDF comprimido: {} -> {} ({:.2f} KB -> {:.2f} KB, reducción {:.1f}%)",
        input_path.name,
        output_path.name,
        in_size / 1024,
        out_size / 1024,
        ratio,
    )
    return output_path