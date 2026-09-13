"""
Regression tests for LFI via ip_content_path on POST /api/projects.
"""
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from config import settings
from src.models.project import Project
from src.utils.path_safety import UnsafePathError, resolve_under_root


@pytest.fixture
def inputs_dir(tmp_path, monkeypatch):
    """Isolate inputs_dir / projects_dir under a temp directory."""
    root = tmp_path / "inputs"
    root.mkdir()
    monkeypatch.setattr(settings, "inputs_dir", root)
    projects = tmp_path / "projects"
    projects.mkdir()
    monkeypatch.setattr(settings, "projects_dir", projects)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    return root


@contextmanager
def _controller_without_llm(config=None):
    """Build PipelineController without initializing LLM-backed modules."""
    from src.pipeline.controller import PipelineController, PipelineConfig

    with (
        patch("src.pipeline.controller.ScriptAdapterModule"),
        patch("src.pipeline.controller.StoryboardModule"),
        patch("src.pipeline.controller.CharacterDesignModule"),
        patch("src.pipeline.controller.ImageGeneratorModule"),
    ):
        yield PipelineController(config=config or PipelineConfig())


class TestResolveUnderRoot:
    def test_rejects_absolute_outside_root(self, inputs_dir):
        with pytest.raises(UnsafePathError):
            resolve_under_root("/etc/passwd", inputs_dir)

    def test_rejects_traversal(self, inputs_dir):
        with pytest.raises(UnsafePathError):
            resolve_under_root(str(inputs_dir / ".." / "passwd"), inputs_dir)

    def test_allows_path_under_root(self, inputs_dir):
        allowed = inputs_dir / "story.txt"
        allowed.write_text("ok", encoding="utf-8")
        resolved = resolve_under_root(str(allowed), inputs_dir)
        assert resolved == allowed.resolve()


class TestCreateProjectPathPolicy:
    @pytest.mark.asyncio
    async def test_controller_rejects_etc_passwd(self, inputs_dir):
        with _controller_without_llm() as controller:
            with pytest.raises(UnsafePathError):
                await controller.create_project(
                    name="lfi",
                    ip_content_path="/etc/passwd",
                )

    @pytest.mark.asyncio
    async def test_controller_rejects_traversal(self, inputs_dir, tmp_path):
        secret = tmp_path / "secret.env"
        secret.write_text("SECRET=1", encoding="utf-8")
        traversal = str(inputs_dir / ".." / "secret.env")
        with _controller_without_llm() as controller:
            with pytest.raises(UnsafePathError):
                await controller.create_project(
                    name="lfi-traversal",
                    ip_content_path=traversal,
                )

    @pytest.mark.asyncio
    async def test_controller_allows_inputs_dir_path(self, inputs_dir):
        allowed = inputs_dir / "ip.txt"
        allowed.write_text("allowed content", encoding="utf-8")
        with _controller_without_llm() as controller:
            project = await controller.create_project(
                name="ok-path",
                ip_content_path=str(allowed),
            )
        assert project.id
        copied = Path(project.project_dir) / "input" / "ip.txt"
        assert copied.exists()
        assert copied.read_text(encoding="utf-8") == "allowed content"

    @pytest.mark.asyncio
    async def test_controller_ip_content_still_works(self, inputs_dir):
        with _controller_without_llm() as controller:
            project = await controller.create_project(
                name="ok-content",
                ip_content="inline story text",
            )
        assert project.id
        assert Path(project.ip_content_path).read_text(encoding="utf-8") == "inline story text"


class TestWebApiIpContentPathLfi:
    @pytest.fixture
    def client(self, inputs_dir):
        from web.app import app

        @asynccontextmanager
        async def _noop_lifespan(_app):
            yield

        original_lifespan = app.router.lifespan_context
        app.router.lifespan_context = _noop_lifespan

        fake_project = Project(
            id="proj_test01",
            name="test",
            ip_name="test",
            project_dir="/tmp/proj_test01",
        )

        async def _fake_create_project(*args, **kwargs):
            return fake_project

        with (
            patch("web.app.PipelineController") as mock_ctrl_cls,
            patch("web.app.controller", MagicMock()),
        ):
            instance = mock_ctrl_cls.return_value
            instance.create_project = AsyncMock(side_effect=_fake_create_project)

            # For allowed-path success we still want real containment + then mock create
            with TestClient(app) as client:
                client._mock_ctrl = instance  # type: ignore[attr-defined]
                yield client

        app.router.lifespan_context = original_lifespan

    def test_api_rejects_etc_passwd(self, client):
        resp = client.post(
            "/api/projects",
            json={"name": "bad", "ip_content_path": "/etc/passwd"},
        )
        assert resp.status_code == 400
        assert "ip_content_path" in resp.json()["detail"]
        client._mock_ctrl.create_project.assert_not_called()

    def test_api_rejects_traversal(self, client, inputs_dir, tmp_path):
        secret = tmp_path / "leak.txt"
        secret.write_text("leak", encoding="utf-8")
        traversal = str(inputs_dir / ".." / "leak.txt")
        resp = client.post(
            "/api/projects",
            json={"name": "bad-trav", "ip_content_path": traversal},
        )
        assert resp.status_code == 400
        client._mock_ctrl.create_project.assert_not_called()

    def test_api_allows_path_under_inputs_dir(self, client, inputs_dir):
        allowed = inputs_dir / "good.txt"
        allowed.write_text("story", encoding="utf-8")
        resp = client.post(
            "/api/projects",
            json={"name": "good", "ip_content_path": str(allowed)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["project_id"] == "proj_test01"
        client._mock_ctrl.create_project.assert_called_once()
        call_kwargs = client._mock_ctrl.create_project.await_args.kwargs
        assert Path(call_kwargs["ip_content_path"]).resolve() == allowed.resolve()

    def test_api_allows_ip_content_without_path(self, client):
        resp = client.post(
            "/api/projects",
            json={"name": "content-only", "ip_content": "hello"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        client._mock_ctrl.create_project.assert_called_once()
