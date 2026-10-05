from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_app_can_be_created() -> None:
    assert app is not None


def test_root_endpoint_returns_expected_payload() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["service"] == settings.app_name
    assert response.json()["status"] == "ok"
    assert response.json()["docs_url"] == "/docs"


def test_health_endpoint_returns_expected_payload() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "service": "DEVDOC",
        "status": "healthy",
    }
