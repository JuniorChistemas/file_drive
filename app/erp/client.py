"""Cliente HTTP para la API del ERP.

Autenticación: POST /api/auth/login devuelve un bearer token que se envía
en el header Authorization de todas las llamadas siguientes.

La subida de documentos es SÍNCRONA: el backend procesa el archivo durante
el POST y la respuesta solo llega cuando termina. Por eso upload_document
usa un timeout largo (ERP_UPLOAD_TIMEOUT) y el caller no debe disparar la
siguiente solicitud hasta recibir cada respuesta.
"""

from pathlib import Path
from typing import Any

import httpx

from app.config.constants import ERP_REQUEST_TIMEOUT, ERP_UPLOAD_TIMEOUT


class ErpError(RuntimeError):
    """Fallo en una llamada a la API del ERP."""


def _extract_token(payload: dict) -> str:
    """Extrae el bearer token de la respuesta de login."""
    data = payload.get("data") or {}
    for token in (
        payload.get("token"),
        payload.get("access_token"),
        data.get("token"),
        data.get("access_token"),
    ):
        if token:
            return str(token)
    raise ErpError(f"La respuesta de login no contiene un token: {sorted(payload)}")


def login(
    base_url: str,
    username: str,
    password: str,
    timeout: float = ERP_REQUEST_TIMEOUT,
    transport: httpx.BaseTransport | None = None,
) -> str:
    """Autentica contra /api/auth/login y devuelve el bearer token."""
    with httpx.Client(
        base_url=base_url.rstrip("/"), timeout=timeout, transport=transport
    ) as client:
        try:
            response = client.post(
                "/api/auth/login",
                json={"username": username, "password": password},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ErpError(f"Login ERP falló: {exc}") from exc
    return _extract_token(response.json())


class ErpClient:
    """Cliente autenticado (bearer token) para los endpoints del ERP."""

    def __init__(
        self,
        base_url: str,
        token: str,
        api_key: str = "",
        timeout: float = ERP_REQUEST_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ):
        self._api_key = api_key
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ErpClient":
        return self

    def __exit__(self, *_exc_info: Any) -> None:
        self.close()

    def get_lot_contracts(self, lot_name: str) -> dict:
        """GET /api/search/contract?lot_name=... → {"data": {lot_id, lot, contracts}}.

        Además del bearer token, envía el header X-API-Token (ERP_API_KEY)
        si está configurado.
        """
        headers = {"X-API-Token": self._api_key} if self._api_key else {}
        try:
            response = self._client.get(
                "/api/search/contract",
                params={"lot_name": lot_name},
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ErpError(f"Consulta del lote '{lot_name}' falló: {exc}") from exc
        return response.json()

    def create_lot_assignment(self, customer_id: int, lot_id: int) -> int:
        """POST /api/panel/lot-assignments → lot_assignments_id."""
        try:
            response = self._client.post(
                "/api/panel/lot-assignments",
                json={"customer_id": customer_id, "lot_id": lot_id},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ErpError(
                f"Creación de lot_assignment (customer_id={customer_id}, "
                f"lot_id={lot_id}) falló: {exc}"
            ) from exc
        payload = response.json()
        assignment_id = payload.get("id")
        if assignment_id is None:
            assignment_id = (payload.get("data") or {}).get("id")
        if assignment_id is None:
            raise ErpError(f"Respuesta sin id de lot_assignment: {payload}")
        return int(assignment_id)

    def upload_document(
        self, lot_assignments_id: int, document_type_id: int, file_path: Path
    ) -> dict:
        """POST /api/panel/assignment-documents (multipart) con status=pending.

        El backend procesa el archivo de forma SÍNCRONA: este POST no
        responde hasta que termina el procesamiento, por lo que se usa un
        timeout largo (ERP_UPLOAD_TIMEOUT, 5 min). El caller debe esperar
        esta respuesta antes de continuar con el siguiente documento.
        """
        file_path = Path(file_path)
        try:
            with open(file_path, "rb") as fh:
                response = self._client.post(
                    "/api/panel/assignment-documents",
                    data={
                        "lot_assignments_id": str(lot_assignments_id),
                        "document_type_id": str(document_type_id),
                        "status": "pending",
                    },
                    files={"file": (file_path.name, fh, "application/pdf")},
                    timeout=ERP_UPLOAD_TIMEOUT,
                )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ErpError(f"Subida de '{file_path.name}' falló: {exc}") from exc
        return response.json()
