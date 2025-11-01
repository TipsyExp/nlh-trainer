"""
Unit tests for the health endpoint exposed by the FastAPI
application.  These tests ensure that the health check returns
HTTP 200 and the expected payload.
"""

from fastapi.testclient import TestClient

from backend.main import app


def test_health_endpoint():
    """Verify that the /health endpoint returns HTTP 200 and a status message."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_endpoint():
    """Verify that the root endpoint returns a welcome message."""
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert "message" in body
    assert "NLH" in body["message"], "Expected NLH training message in response"
