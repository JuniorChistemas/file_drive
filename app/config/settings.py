import json
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Google Drive API
    google_credentials_path: Path
    drive_root_folder: str = "CARPETA_PRUEBA"  # 'Escaneos'
    drive_manzana_folder: str = "SUB_CARPETA"  # subcarpeta de manzana bajo la raíz

    # ERP
    erp_api_url: str = ""
    erp_api_key: str = ""
    erp_username: str = ""
    erp_password: str = ""

    # Pipeline: reanudar desde un lote dado (inclusive); vacío = procesar todos.
    # Útil para recuperar una corrida interrumpida sin duplicar lot_assignments
    # de lotes ya subidos al ERP (el ERP no deduplica).
    pipeline_start_from_lote: str = ""

    # Logging
    log_level: str = "INFO"

    @field_validator("google_credentials_path")
    @classmethod
    def credentials_must_be_service_account(cls, value: Path) -> Path:
        if not value.exists():
            raise ValueError(f"Archivo de credenciales no encontrado: {value}")
        try:
            data = json.loads(value.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"El archivo de credenciales no es JSON válido: {exc}") from exc
        if data.get("type") != "service_account":
            raise ValueError(
                f"{value} no es una clave de service account "
                f"(type={data.get('type')!r}). Descarga la clave JSON de una "
                "service account desde Google Cloud Console."
            )
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
