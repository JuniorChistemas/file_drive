"""Construcción del cliente de Google Drive API con service account."""

from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.config.constants import DRIVE_SCOPES
from app.config.settings import get_settings


def build_drive_service():
    """Crea el servicio de Drive v3 autenticado con la service account."""
    settings = get_settings()
    credentials = service_account.Credentials.from_service_account_file(
        str(settings.google_credentials_path),
        scopes=DRIVE_SCOPES,
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)
