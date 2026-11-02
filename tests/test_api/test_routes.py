"""
Unit tests for FastAPI REST endpoints (src/api/app.py).
"""

import pytest
from fastapi.testclient import TestClient

from src.api.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    """GET /health should return 200 with status ok."""
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_root_health(client):
    """GET / should return 200 online."""
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"
    assert data["version"] == "1.0.0"


def test_get_metadata_endpoint(client):
    """GET /api/v1/metadata should return data scope banner data."""
    res = client.get("/api/v1/metadata")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    scope = data["data"]
    assert "total_filtered_items" in scope
    assert "sources" in scope
    assert "known_biases" in scope


def test_get_opportunities_endpoint(client):
    """GET /api/v1/opportunities should return ranked opportunity areas."""
    res = client.get("/api/v1/opportunities")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert isinstance(data["data"], list)
    if data["data"]:
        first = data["data"][0]
        assert "theme_name" in first
        assert "composite_score" in first
        assert "evidence_level" in first


def test_chat_endpoint_normal_query(client):
    """POST /api/v1/chat with valid research query."""
    payload = {"query": "What confuses investors about XIRR?"}
    res = client.post("/api/v1/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["intent"] in ["count_query", "exploration_query", "drill_down"]
    assert len(data["answer"]) > 10


def test_chat_endpoint_refusal_query(client):
    """POST /api/v1/chat with forbidden investment advice query."""
    payload = {"query": "Which mutual fund should I invest in?"}
    res = client.post("/api/v1/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["intent"] == "refusal"
    assert "not to recommend specific funds" in data["answer"].lower()


def test_get_evidence_log_endpoint(client):
    """GET /api/v1/evidence-log should return audit trail entries."""
    res = client.get("/api/v1/evidence-log")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert isinstance(data["data"], list)

