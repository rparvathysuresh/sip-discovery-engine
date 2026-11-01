"""
Unit tests for UI static file serving and browser routing (Phase 7 - Task 7.9).
"""

import pytest
from fastapi.testclient import TestClient

from src.api.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_api_root_json(client):
    """GET / with API client returns JSON metadata."""
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"
    assert data["version"] == "1.0.0"


def test_browser_root_html(client):
    """GET / with Accept: text/html returns the UI index.html."""
    res = client.get("/", headers={"accept": "text/html,application/xhtml+xml"})
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "SIP Investor Discovery Engine" in res.text
    assert "Assistant Chat" in res.text
    assert "Opportunity Explorer" in res.text


def test_index_html_endpoint(client):
    """GET /index.html serves index.html."""
    res = client.get("/index.html")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "data-scope-banner" in res.text


def test_css_static_serving(client):
    """GET /css/main.css returns CSS file."""
    res = client.get("/css/main.css")
    assert res.status_code == 200
    assert "text/css" in res.headers.get("content-type", "")
    assert "--bg-primary" in res.text


def test_js_static_serving(client):
    """GET /js/app.js returns JavaScript file."""
    res = client.get("/js/app.js")
    assert res.status_code == 200
    assert "loadDataScopeBanner" in res.text


def test_ui_mount_serving(client):
    """GET /ui/index.html returns index.html through mounted directory."""
    res = client.get("/ui/index.html")
    assert res.status_code == 200
    assert "SIP Investor Discovery Engine" in res.text

