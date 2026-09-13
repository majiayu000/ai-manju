"""
Tests for path traversal hardening in path_safety and web API file routes.
"""
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.utils.path_safety import UnsafePathError, safe_join_under, validate_path_segment


class TestValidatePathSegment:
    def test_accepts_safe_segments(self):
        assert validate_path_segment("my_project-01") == "my_project-01"
        assert validate_path_segment("file.png") == "file.png"
        assert validate_path_segment("images") == "images"

    @pytest.mark.parametrize(
        "segment",
        [
            "..",
            ".",
            "",
            "../..",
            "../../.env",
            "foo/bar",
            "foo\\bar",
            "has space",
            "weird$chars",
            "a/../b",
        ],
    )
    def test_rejects_unsafe_segments(self, segment):
        with pytest.raises(UnsafePathError):
            validate_path_segment(segment)


class TestSafeJoinUnder:
    def test_joins_under_root(self, tmp_path: Path):
        root = tmp_path / "projects"
        root.mkdir()
        target = root / "proj1" / "images"
        target.mkdir(parents=True)

        result = safe_join_under(root, "proj1", "images")
        assert result == target.resolve()
        assert result.is_relative_to(root.resolve())

    def test_rejects_traversal_via_project_id(self, tmp_path: Path):
        root = tmp_path / "projects"
        root.mkdir()
        (tmp_path / "secret.txt").write_text("secret")

        with pytest.raises(UnsafePathError):
            safe_join_under(root, "..", "secret.txt")

    def test_rejects_traversal_via_filename(self, tmp_path: Path):
        root = tmp_path / "projects"
        (root / "proj1").mkdir(parents=True)

        with pytest.raises(UnsafePathError):
            safe_join_under(root, "proj1", "images", "../../secret.txt")

    def test_resolved_path_stays_under_root(self, tmp_path: Path):
        root = tmp_path / "projects"
        root.mkdir()
        # Symlink escape: resolved path must still be rejected when outside root.
        outside = tmp_path / "outside"
        outside.mkdir()
        link = root / "escape"
        link.symlink_to(outside)

        with pytest.raises(UnsafePathError):
            safe_join_under(root, "escape", "file.txt")


def _build_secured_app(projects_dir: Path) -> FastAPI:
    """
    Mirror the secured join pattern used by web/app.py endpoints so API-level
    traversal behavior can be tested without importing the full pipeline graph
    (which currently has an unrelated SyntaxError in character designer).
    """
    import shutil

    from fastapi.responses import FileResponse

    app = FastAPI()

    @app.delete("/api/projects/{project_id}")
    async def delete_project(project_id: str):
        try:
            project_dir = safe_join_under(projects_dir, project_id)
        except UnsafePathError:
            raise HTTPException(status_code=400, detail="无效的项目路径")
        if not project_dir.exists():
            raise HTTPException(status_code=404, detail="项目不存在")
        shutil.rmtree(project_dir)
        return {"success": True}

    @app.get("/api/projects/{project_id}/preview/images")
    async def preview_images(project_id: str, episode: int = 1):
        try:
            project_dir = safe_join_under(projects_dir, project_id, "images")
        except UnsafePathError:
            raise HTTPException(status_code=400, detail="无效的项目路径")
        if not project_dir.exists():
            return {"images": []}
        images = []
        for img_file in sorted(project_dir.glob(f"ep{episode:02d}_*.png")):
            images.append(
                {
                    "name": img_file.name,
                    "path": f"/api/projects/{project_id}/files/images/{img_file.name}",
                }
            )
        return {"images": images}

    @app.get("/api/projects/{project_id}/files/{category}/{filename}")
    async def get_file(project_id: str, category: str, filename: str):
        try:
            file_path = safe_join_under(
                projects_dir, project_id, category, filename
            )
        except UnsafePathError:
            raise HTTPException(status_code=400, detail="无效的文件路径")
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")
        return FileResponse(file_path)

    return app


@pytest.fixture
def api_client(tmp_path: Path):
    projects = tmp_path / "projects"
    projects.mkdir()
    proj = projects / "demo_proj"
    images = proj / "images"
    images.mkdir(parents=True)
    (images / "ep01_shot01.png").write_bytes(b"png-bytes")
    (proj / "meta.json").write_text("{}")

    # Secret outside projects_dir — must never be readable/deletable via API
    secret = tmp_path / ".env"
    secret.write_text("SECRET=1")

    client = TestClient(_build_secured_app(projects))
    return client, projects, secret


class TestWebAppWiresPathSafety:
    def test_app_source_uses_safe_join(self):
        app_src = Path(__file__).resolve().parents[1] / "web" / "app.py"
        text = app_src.read_text(encoding="utf-8")
        assert "from src.utils.path_safety import UnsafePathError, safe_join_under" in text
        assert text.count("safe_join_under(") >= 3


class TestFileApiPathSafety:
    def test_get_file_happy_path(self, api_client):
        client, _projects, _secret = api_client
        resp = client.get("/api/projects/demo_proj/files/images/ep01_shot01.png")
        assert resp.status_code == 200
        assert resp.content == b"png-bytes"

    @pytest.mark.parametrize(
        "url",
        [
            # Encoded ".." so the client does not normalize the URL away from the route
            "/api/projects/%2e%2e/files/images/x.png",
            "/api/projects/demo_proj/files/images/%2e%2e%2e%2e%2f.env",
            "/api/projects/%2e%2e%2f%2e%2e/files/images/x.png",
            "/api/projects/demo_proj/files/%2e%2e/x.png",
            "/api/projects/bad$id/files/images/x.png",
        ],
    )
    def test_get_file_rejects_traversal(self, api_client, url):
        client, projects, secret = api_client
        resp = client.get(url)
        assert resp.status_code in {400, 404}
        # Must not leak secret contents
        assert resp.content != secret.read_bytes()
        assert secret.exists()
        assert projects.exists()

    def test_delete_project_happy_path(self, api_client):
        client, projects, _secret = api_client
        target = projects / "to_delete"
        target.mkdir()
        (target / "keep.txt").write_text("x")

        resp = client.delete("/api/projects/to_delete")
        assert resp.status_code == 200
        assert not target.exists()

    def test_delete_project_rejects_traversal(self, api_client, tmp_path):
        client, projects, secret = api_client
        outside_dir = tmp_path / "must_survive"
        outside_dir.mkdir()
        (outside_dir / "marker").write_text("ok")

        resp = client.delete("/api/projects/%2e%2e%2f%2e%2e%2fmust_survive")
        assert resp.status_code in {400, 404}
        assert outside_dir.exists()
        assert secret.exists()
        assert projects.exists()

    def test_preview_images_rejects_bad_project_id(self, api_client):
        client, _projects, _secret = api_client
        resp = client.get("/api/projects/%2e%2e/preview/images")
        assert resp.status_code in {400, 404}

    def test_preview_images_happy_path(self, api_client):
        client, _projects, _secret = api_client
        resp = client.get("/api/projects/demo_proj/preview/images")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["images"]) == 1
        assert data["images"][0]["name"] == "ep01_shot01.png"
