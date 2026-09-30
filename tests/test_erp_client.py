"""Tests de app.erp.client con transporte mock de httpx (sin red)."""

import json

import httpx
import pytest

from app.config.constants import ERP_UPLOAD_TIMEOUT
from app.erp.client import ErpClient, ErpError, login

BASE_URL = "http://erp.test"
TOKEN = "tok123"
API_KEY = "key456"


def _client(handler, api_key: str = "") -> ErpClient:
    return ErpClient(BASE_URL, TOKEN, api_key=api_key, transport=httpx.MockTransport(handler))


class TestLogin:
    def test_login_ok(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/auth/login"
            assert "authorization" not in request.headers
            body = json.loads(request.content)
            assert body == {"username": "admin", "password": "secret"}
            return httpx.Response(200, json={"access_token": TOKEN})

        token = login(BASE_URL, "admin", "secret", transport=httpx.MockTransport(handler))
        assert token == TOKEN

    def test_login_token_en_data(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": {"token": TOKEN}})

        token = login(BASE_URL, "admin", "secret", transport=httpx.MockTransport(handler))
        assert token == TOKEN

    def test_login_credenciales_invalidas(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"message": "unauthorized"})

        with pytest.raises(ErpError, match="Login ERP falló"):
            login(BASE_URL, "admin", "wrong", transport=httpx.MockTransport(handler))

    def test_login_respuesta_sin_token(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"message": "ok"})

        with pytest.raises(ErpError, match="no contiene un token"):
            login(BASE_URL, "admin", "secret", transport=httpx.MockTransport(handler))


class TestGetLotContracts:
    def test_consulta_por_lote(self):
        payload = {
            "data": {
                "lot_id": 17,
                "lot": "A-17",
                "contracts": [
                    {
                        "correlative": "202601-000001343",
                        "customer": {"customer_id": 535, "document_number": "03502322"},
                    }
                ],
            }
        }

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/search/contract"
            assert request.url.params["lot_name"] == "A-17"
            assert request.headers["Authorization"] == f"Bearer {TOKEN}"
            assert request.headers["X-API-Token"] == API_KEY
            return httpx.Response(200, json=payload)

        with _client(handler, api_key=API_KEY) as client:
            result = client.get_lot_contracts("A-17")

        assert result["data"]["lot_id"] == 17
        assert len(result["data"]["contracts"]) == 1

    def test_sin_api_key_no_envia_el_header(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/search/contract"
            assert "x-api-token" not in request.headers
            return httpx.Response(200, json={"data": {"lot_id": 17, "contracts": []}})

        with _client(handler) as client:
            assert client.get_lot_contracts("A-17")["data"]["lot_id"] == 17

    def test_lote_no_encontrado(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"message": "not found"})

        with _client(handler) as client, pytest.raises(ErpError, match="A-99"):
            client.get_lot_contracts("A-99")


class TestCreateLotAssignment:
    def test_crea_assignment_id_plano(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/panel/lot-assignments"
            assert request.headers["Authorization"] == f"Bearer {TOKEN}"
            assert json.loads(request.content) == {"customer_id": 535, "lot_id": 17}
            return httpx.Response(201, json={"id": 42})

        with _client(handler) as client:
            assert client.create_lot_assignment(535, 17) == 42

    def test_crea_assignment_id_en_data(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(201, json={"data": {"id": 43}})

        with _client(handler) as client:
            assert client.create_lot_assignment(535, 17) == 43

    def test_respuesta_sin_id(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(201, json={"message": "created"})

        with _client(handler) as client, pytest.raises(ErpError, match="sin id"):
            client.create_lot_assignment(535, 17)

    def test_error_de_validacion(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(422, json={"message": "invalid"})

        with _client(handler) as client, pytest.raises(ErpError):
            client.create_lot_assignment(535, 17)


class TestUploadDocument:
    def test_subida_multipart(self, tmp_path):
        pdf = tmp_path / "73439516_CONTRATO_A-19_compressed.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake-content")

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/panel/assignment-documents"
            assert request.headers["Authorization"] == f"Bearer {TOKEN}"
            content_type = request.headers["Content-Type"]
            assert content_type.startswith("multipart/form-data")
            body = request.content
            assert b'name="lot_assignments_id"' in body
            assert b"\r\n\r\n42\r\n" in body
            assert b'name="document_type_id"' in body
            assert b"\r\n\r\n4\r\n" in body
            assert b'name="status"' in body
            assert b"\r\n\r\npending\r\n" in body
            assert b'filename="73439516_CONTRATO_A-19_compressed.pdf"' in body
            assert b"%PDF-1.4 fake-content" in body
            return httpx.Response(201, json={"id": 7})

        with _client(handler) as client:
            result = client.upload_document(42, 4, pdf)

        assert result["id"] == 7

    def test_error_de_subida(self, tmp_path):
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"message": "server error"})

        with _client(handler) as client, pytest.raises(ErpError, match="doc.pdf"):
            client.upload_document(42, 4, pdf)

    def test_timeout_de_subida_se_envuelve_en_erp_error(self, tmp_path):
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("read timed out (5 min agotados)")

        with _client(handler) as client, pytest.raises(ErpError, match="doc.pdf"):
            client.upload_document(42, 4, pdf)


class TestTimeouts:
    """La subida es síncrona: usa timeout largo; el resto mantiene el default."""

    @staticmethod
    def _spy_post(monkeypatch) -> list:
        """Espía httpx.Client.post registrando el timeout de cada llamada."""
        recorded: list = []
        original_post = httpx.Client.post

        def spy_post(self, url, **kwargs):
            recorded.append(kwargs.get("timeout"))
            return original_post(self, url, **kwargs)

        monkeypatch.setattr(httpx.Client, "post", spy_post)
        return recorded

    def test_upload_envia_timeout_largo(self, tmp_path, monkeypatch):
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        recorded = self._spy_post(monkeypatch)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(201, json={"id": 7})

        with _client(handler) as client:
            client.upload_document(42, 4, pdf)

        assert recorded == [ERP_UPLOAD_TIMEOUT]

    def test_otros_endpoints_mantienen_timeout_default(self, monkeypatch):
        recorded = self._spy_post(monkeypatch)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(201, json={"id": 42})

        with _client(handler) as client:
            client.create_lot_assignment(535, 17)

        assert recorded == [None]
