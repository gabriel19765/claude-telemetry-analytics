"""Unit tests for FastAPI endpoints in src/api.py."""

from fastapi.testclient import TestClient
from src.api import app

client = TestClient(app)


def test_health_check_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert "status" in response.json()


def test_kpis_endpoint():
    response = client.get("/api/v1/metrics/kpis")
    assert response.status_code in [200, 530, 503]
    if response.status_code == 200:
        data = response.json()
        assert "total_cost_usd" in data
        assert "total_tokens" in data


def test_anomalies_summary_endpoint():
    response = client.get("/api/v1/anomalies/summary")
    assert response.status_code in [200, 503]
