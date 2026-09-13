"""
Tests for web API key authentication and secure defaults.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from config import settings
from config.settings import Settings
from web.app import app, start_server
from web.auth import require_api_key


TEST_API_KEY = "test-secret-api-key-for-auth"


@pytest.fixture
def client(monkeypatch):
    """TestClient with a configured API key; avoid real pipeline init."""
    monkeypatch.setattr(settings, "api_key", TEST_API_KEY)
    with patch("web.app.PipelineController", return_value=MagicMock()):
        with TestClient(app) as test_client:
            yield test_client


@pytest.fixture
def auth_headers():
    return {"X-API-Key": TEST_API_KEY}


def test_settings_host_defaults_to_localhost():
    assert Settings.model_fields["host"].default == "127.0.0.1"
    assert Settings.model_fields["debug"].default is False


def test_start_server_uses_settings_host_port(monkeypatch):
    monkeypatch.setattr(settings, "host", "127.0.0.1")
    monkeypatch.setattr(settings, "port", 8765)
    called = {}

    def fake_run(app_arg, host=None, port=None):
        called["host"] = host
        called["port"] = port

    with patch("uvicorn.run", side_effect=fake_run):
        start_server()

    assert called["host"] == "127.0.0.1"
    assert called["port"] == 8765


@pytest.mark.parametrize(
    "method,path,json_body",
    [
        ("post", "/api/projects", {"name": "auth-test"}),
        ("delete", "/api/projects/proj-1", None),
        ("post", "/api/projects/proj-1/pipeline/start", {}),
        ("post", "/api/projects/proj-1/modules/script/run", {"stage": "script"}),
    ],
)
def test_mutating_routes_require_api_key(client, method, path, json_body):
    request = getattr(client, method)
    kwargs = {}
    if json_body is not None:
        kwargs["json"] = json_body
    response = request(path, **kwargs)
    assert response.status_code == 401


@pytest.mark.parametrize(
    "method,path,json_body",
    [
        ("post", "/api/projects", {"name": "auth-test"}),
        ("delete", "/api/projects/proj-1", None),
        ("post", "/api/projects/proj-1/pipeline/start", {}),
        ("post", "/api/projects/proj-1/modules/script/run", {"stage": "script"}),
    ],
)
def test_mutating_routes_reject_invalid_api_key(client, method, path, json_body):
    request = getattr(client, method)
    kwargs = {"headers": {"X-API-Key": "wrong-key"}}
    if json_body is not None:
        kwargs["json"] = json_body
    response = request(path, **kwargs)
    assert response.status_code == 401


def test_create_project_succeeds_with_valid_api_key(client, auth_headers):
    fake_project = type("P", (), {"id": "p1", "project_dir": "/tmp/p1"})()

    with patch("web.app.PipelineController") as mock_ctrl_cls:
        instance = mock_ctrl_cls.return_value
        instance.create_project = AsyncMock(return_value=fake_project)
        response = client.post(
            "/api/projects",
            json={"name": "secure-project"},
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["project_id"] == "p1"


def test_delete_project_auth_passes_then_not_found(client, auth_headers, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "projects_dir", tmp_path)
    response = client.delete("/api/projects/missing-project", headers=auth_headers)
    # Auth succeeded; project missing yields 404 (not 401).
    assert response.status_code == 404


def test_start_pipeline_auth_passes_then_not_found(client, auth_headers):
    with patch("web.app.controller") as mock_controller:
        mock_controller.load_project = AsyncMock(side_effect=FileNotFoundError())
        response = client.post(
            "/api/projects/missing/pipeline/start",
            json={},
            headers=auth_headers,
        )
    assert response.status_code == 404


def test_run_module_auth_passes_then_not_found(client, auth_headers):
    with patch("web.app.controller") as mock_controller:
        mock_controller.load_project = AsyncMock(side_effect=FileNotFoundError())
        response = client.post(
            "/api/projects/missing/modules/script/run",
            json={"stage": "script"},
            headers=auth_headers,
        )
    assert response.status_code == 404


def test_require_api_key_dependency_is_wired():
    """Mutating route dependencies include require_api_key."""
    mutating_paths = {
        ("POST", "/api/projects"),
        ("DELETE", "/api/projects/{project_id}"),
        ("POST", "/api/projects/{project_id}/pipeline/start"),
        ("POST", "/api/projects/{project_id}/modules/{module}/run"),
    }
    found = set()
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", None)
        for method in methods:
            key = (method, path)
            if key in mutating_paths:
                dependant = route.dependant
                dep_calls = [d.call for d in dependant.dependencies]
                assert require_api_key in dep_calls
                found.add(key)
    assert found == mutating_paths


def test_list_projects_remains_unauthenticated(client):
    """Read-only listing is not gated by API key in this change."""
    response = client.get("/api/projects")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
