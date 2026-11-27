from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from guitarcv_restapi.api.dependencies import get_conversion_service
from guitarcv_restapi.api.v1.router import router as v1_router
from guitarcv_restapi.core.exception_handlers import register_exception_handlers
from guitarcv_restapi.models.conversion import Conversion, ConversionStatus


class FakeConversionService:
    def __init__(self, conversion) -> None:
        self.conversion = conversion

    def get_conversion(self, conversion_id: str):
        if self.conversion and self.conversion.conversion_id == conversion_id:
            return self.conversion
        return None


def make_test_app(service: FakeConversionService) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(v1_router, prefix="/api/v1")
    app.dependency_overrides[get_conversion_service] = lambda: service
    return app


def test_expired_result_returns_410_with_standard_error_envelope() -> None:
    now = datetime.now(timezone.utc)
    conversion = Conversion(
        conversion_id="c" * 32,
        status=ConversionStatus.READY,
        created_at=now - timedelta(hours=2),
        updated_at=now,
        input_path=None,
        result_expires_at=now - timedelta(seconds=1),
    )
    client = TestClient(make_test_app(FakeConversionService(conversion)))

    response = client.get(
        "/api/v1/conversions/%s/result" % conversion.conversion_id
    )

    assert response.status_code == 410
    assert response.json() == {
        "status": "error",
        "error": {
            "code": "RESULT_EXPIRED",
            "message": "The MIDI result has expired and is no longer available.",
        },
    }


def test_method_not_allowed_uses_standard_error_envelope() -> None:
    client = TestClient(make_test_app(FakeConversionService(None)))

    response = client.post("/api/v1/conversions/anything")

    assert response.status_code == 405
    assert response.json()["status"] == "error"
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert "Allow" in response.headers


def test_ready_conversion_cannot_serve_a_file_outside_configured_result_storage(
    tmp_path,
) -> None:
    now = datetime.now(timezone.utc)
    external_file = tmp_path / "private.txt"
    external_file.write_text("must not be served", encoding="utf-8")
    conversion = Conversion(
        conversion_id="d" * 32,
        status=ConversionStatus.READY,
        created_at=now - timedelta(minutes=1),
        updated_at=now,
        input_path=None,
        result_path=external_file,
        result_expires_at=now + timedelta(hours=1),
    )
    client = TestClient(make_test_app(FakeConversionService(conversion)))

    response = client.get(
        "/api/v1/conversions/%s/result" % conversion.conversion_id
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "RESULT_FILE_PATH_INVALID"
    assert "must not be served" not in response.text
