"""Constantes del proyecto."""

# Google Drive API
# Nota: cuando se implementen upload/move, ampliar a
# "https://www.googleapis.com/auth/drive"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
DRIVE_PAGE_SIZE = 1000
DRIVE_FILE_FIELDS = "nextPageToken, files(id, name, mimeType, size, modifiedTime, parents)"

# MIME types
MIME_FOLDER = "application/vnd.google-apps.folder"
MIME_PDF = "application/pdf"
