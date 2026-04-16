"""아이콘 업로드 엔드포인트 단위 테스트 (TDD)

테스트 범위:
1. 정상 업로드 — 파일이 올바른 경로에 저장되고 widget_config.button_icon_url이 갱신됨
2. 잘못된 MIME 타입 — 400 반환
3. 파일 크기 초과 — 400 반환
4. 기존 아이콘 교체 — 이전 파일 삭제 후 새 파일 저장
5. 아이콘 삭제 — widget_config에서 button_icon_url 제거 및 파일 삭제
6. ICONS_DIR 경로 계산 — tenants.py와 main.py의 ICONS_DIR이 동일한 경로를 가리킴
"""

import io
import pathlib
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ─── Fixtures ────────────────────────────────────────────────────────────────


def make_tenant(
    tenant_id: int = 1,
    widget_config: dict | None = None,
    api_key: str = "tenant_test",
) -> MagicMock:
    """Mock Tenant 객체 생성 헬퍼"""
    t = MagicMock()
    t.id = tenant_id
    t.api_key = api_key
    t.name = "테스트 테넌트"
    t.is_active = True
    t.lang_policy = "auto"
    t.default_lang = "ko"
    t.allowed_langs = "ko,en"
    t.allowed_domains = ""
    t.system_prompt = None
    t.default_url_refresh_hours = 0
    t.langsmith_api_key = None
    t.widget_config = widget_config if widget_config is not None else {"primary_color": "#0066ff"}
    return t


def png_bytes(size: int = 100) -> bytes:
    """최소한의 PNG 파일 바이트 생성"""
    # 1×1 픽셀 PNG (실제 파일 시그니처 포함)
    return (
        b"\x89PNG\r\n\x1a\n"  # PNG signature
        b"\x00\x00\x00\rIHDR"  # IHDR chunk
        b"\x00\x00\x00\x01\x00\x00\x00\x01"  # 1x1
        b"\x08\x02\x00\x00\x00\x90wS\xde"  # bit depth, color type, etc.
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )


# ─── ICONS_DIR 경로 일관성 테스트 ─────────────────────────────────────────────


class TestIconsDirPath:
    """ICONS_DIR 경로가 tenants.py와 main.py에서 동일해야 한다"""

    def test_tenants_icons_dir_resolves_correctly(self):
        """tenants.py의 ICONS_DIR이 static/icons를 가리킴"""
        import app.routers.tenants as tenants_module

        icons_dir = tenants_module.ICONS_DIR
        # 경로의 마지막 두 부분이 static/icons 여야 함
        assert icons_dir.parts[-1] == "icons"
        assert icons_dir.parts[-2] == "static"

    def test_main_icons_dir_resolves_correctly(self):
        """main.py의 ICONS_DIR이 static/icons를 가리킴"""
        import app.main as main_module

        icons_dir = main_module.ICONS_DIR
        assert icons_dir.parts[-1] == "icons"
        assert icons_dir.parts[-2] == "static"

    def test_tenants_and_main_icons_dir_are_same_path(self):
        """tenants.py와 main.py의 ICONS_DIR이 동일한 절대 경로를 가리켜야 한다"""
        import app.main as main_module
        import app.routers.tenants as tenants_module

        assert tenants_module.ICONS_DIR.resolve() == main_module.ICONS_DIR.resolve()


# ─── 업로드 엔드포인트 단위 테스트 ───────────────────────────────────────────


class TestIconUploadEndpoint:
    """POST /api/v1/tenants/{id}/icon 엔드포인트 테스트"""

    def _make_app_with_mock_db(self, mock_tenant: MagicMock):
        """TestClient에서 사용할 FastAPI 앱 설정"""
        from fastapi import FastAPI
        from app.routers.tenants import router
        from app.db.session import get_db
        from app.middleware.auth import verify_admin

        app = FastAPI()
        app.include_router(router)

        async def override_db():
            db = AsyncMock()
            db.get = AsyncMock(return_value=mock_tenant)
            db.flush = AsyncMock()
            db.refresh = AsyncMock()
            db.commit = AsyncMock()
            yield db

        async def override_admin():
            return None

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[verify_admin] = override_admin
        return app

    def test_upload_valid_png_saves_file_and_updates_widget_config(self, tmp_path):
        """PNG 업로드 시 파일이 저장되고 widget_config.button_icon_url이 갱신된다 (RED)"""
        tenant = make_tenant()
        app = self._make_app_with_mock_db(tenant)

        with patch("app.routers.tenants.ICONS_DIR", tmp_path):
            client = TestClient(app)
            response = client.post(
                "/api/v1/tenants/1/icon",
                files={"file": ("test.png", png_bytes(), "image/png")},
            )

        assert response.status_code == 200
        data = response.json()
        assert "button_icon_url" in data["widget_config"]
        icon_url: str = data["widget_config"]["button_icon_url"]
        assert icon_url.startswith("/rag/static/icons/")
        assert icon_url.endswith(".png")

        # 실제 파일이 tmp_path에 저장됐는지 확인
        saved_filename = icon_url.split("/")[-1]
        assert (tmp_path / saved_filename).exists()

    def test_upload_invalid_mime_type_returns_400(self, tmp_path):
        """허용되지 않은 MIME 타입 업로드 시 400 반환 (RED)"""
        tenant = make_tenant()
        app = self._make_app_with_mock_db(tenant)

        with patch("app.routers.tenants.ICONS_DIR", tmp_path):
            client = TestClient(app)
            response = client.post(
                "/api/v1/tenants/1/icon",
                files={"file": ("test.txt", b"hello", "text/plain")},
            )

        assert response.status_code == 400
        assert "이미지" in response.json()["detail"]

    def test_upload_oversized_file_returns_400(self, tmp_path):
        """2MB 초과 파일 업로드 시 400 반환 (RED)"""
        tenant = make_tenant()
        app = self._make_app_with_mock_db(tenant)

        oversized = b"x" * (2 * 1024 * 1024 + 1)
        with patch("app.routers.tenants.ICONS_DIR", tmp_path):
            client = TestClient(app)
            response = client.post(
                "/api/v1/tenants/1/icon",
                files={"file": ("big.png", oversized, "image/png")},
            )

        assert response.status_code == 400
        assert "2MB" in response.json()["detail"]

    def test_upload_replaces_existing_icon(self, tmp_path):
        """기존 아이콘이 있을 때 교체 시 이전 파일을 삭제한다 (RED)"""
        # 이전 아이콘 파일 생성
        old_filename = "tenant_1_old.png"
        old_file = tmp_path / old_filename
        old_file.write_bytes(b"old icon data")

        tenant = make_tenant(
            widget_config={"button_icon_url": f"/rag/static/icons/{old_filename}"}
        )
        app = self._make_app_with_mock_db(tenant)

        with patch("app.routers.tenants.ICONS_DIR", tmp_path):
            client = TestClient(app)
            response = client.post(
                "/api/v1/tenants/1/icon",
                files={"file": ("new.png", png_bytes(), "image/png")},
            )

        assert response.status_code == 200
        # 이전 파일이 삭제됐는지 확인
        assert not old_file.exists()

    def test_upload_webp_preserves_extension(self, tmp_path):
        """WebP 파일 업로드 시 .webp 확장자 유지 (RED)"""
        tenant = make_tenant()
        app = self._make_app_with_mock_db(tenant)

        with patch("app.routers.tenants.ICONS_DIR", tmp_path):
            client = TestClient(app)
            response = client.post(
                "/api/v1/tenants/1/icon",
                files={"file": ("icon.webp", b"webp_data", "image/webp")},
            )

        assert response.status_code == 200
        icon_url: str = response.json()["widget_config"]["button_icon_url"]
        assert icon_url.endswith(".webp")


# ─── 아이콘 삭제 엔드포인트 테스트 ───────────────────────────────────────────


class TestIconDeleteEndpoint:
    """DELETE /api/v1/tenants/{id}/icon 엔드포인트 테스트"""

    def _make_app_with_mock_db(self, mock_tenant: MagicMock):
        from fastapi import FastAPI
        from app.routers.tenants import router
        from app.db.session import get_db
        from app.middleware.auth import verify_admin

        app = FastAPI()
        app.include_router(router)

        async def override_db():
            db = AsyncMock()
            db.get = AsyncMock(return_value=mock_tenant)
            db.flush = AsyncMock()
            db.refresh = AsyncMock()
            db.commit = AsyncMock()
            yield db

        async def override_admin():
            return None

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[verify_admin] = override_admin
        return app

    def test_delete_icon_removes_button_icon_url_from_widget_config(self, tmp_path):
        """아이콘 삭제 시 widget_config에서 button_icon_url 제거 (RED)"""
        filename = "tenant_1_icon.png"
        icon_file = tmp_path / filename
        icon_file.write_bytes(b"icon data")

        tenant = make_tenant(
            widget_config={"button_icon_url": f"/rag/static/icons/{filename}"}
        )
        app = self._make_app_with_mock_db(tenant)

        with patch("app.routers.tenants.ICONS_DIR", tmp_path):
            client = TestClient(app)
            response = client.delete("/api/v1/tenants/1/icon")

        assert response.status_code == 200
        assert "button_icon_url" not in response.json()["widget_config"]
        # 파일도 삭제됐는지 확인
        assert not icon_file.exists()

    def test_delete_icon_when_no_icon_set_returns_200(self, tmp_path):
        """아이콘이 없는 상태에서 삭제 요청 시 200 반환 (RED)"""
        tenant = make_tenant(widget_config={"primary_color": "#0066ff"})
        app = self._make_app_with_mock_db(tenant)

        with patch("app.routers.tenants.ICONS_DIR", tmp_path):
            client = TestClient(app)
            response = client.delete("/api/v1/tenants/1/icon")

        assert response.status_code == 200


# ─── widget-config 엔드포인트 — button_icon_url 포함 테스트 ──────────────────


class TestWidgetConfigIncludesIconUrl:
    """GET /api/v1/chat/widget-config가 button_icon_url을 포함해야 한다"""

    def test_widget_config_returns_button_icon_url_when_set(self):
        """widget_config에 button_icon_url이 있으면 응답에 포함 (RED)"""
        from fastapi import FastAPI
        from app.routers.chat import router
        from app.middleware.auth import get_tenant

        app = FastAPI()
        app.include_router(router)

        tenant = make_tenant(
            widget_config={
                "primary_color": "#ff0000",
                "button_icon_url": "/rag/static/icons/tenant_1_abc.png",
            }
        )

        async def override_tenant():
            return tenant

        app.dependency_overrides[get_tenant] = override_tenant

        client = TestClient(app)
        response = client.get("/api/v1/chat/widget-config", headers={"X-API-Key": "test"})

        assert response.status_code == 200
        data = response.json()
        assert "button_icon_url" in data
        assert data["button_icon_url"] == "/rag/static/icons/tenant_1_abc.png"

    def test_widget_config_omits_button_icon_url_when_not_set(self):
        """widget_config에 button_icon_url이 없으면 응답에도 없어야 함 (RED)"""
        from fastapi import FastAPI
        from app.routers.chat import router
        from app.middleware.auth import get_tenant

        app = FastAPI()
        app.include_router(router)

        tenant = make_tenant(widget_config={"primary_color": "#0066ff"})

        async def override_tenant():
            return tenant

        app.dependency_overrides[get_tenant] = override_tenant

        client = TestClient(app)
        response = client.get("/api/v1/chat/widget-config", headers={"X-API-Key": "test"})

        assert response.status_code == 200
        assert "button_icon_url" not in response.json()


# ─── 프록시 라우팅 경로 검증 ────────────────────────────────────────────────


class TestProxyRoutingPath:
    """admin proxy가 올바른 FastAPI 경로를 사용하는지 검증

    Docker 내부 direct call: http://api:8000/api/v1/...  (nginx 없음, /rag 없음)
    nginx를 통한 외부 call:   /rag/api/v1/...            (nginx가 /rag 제거)

    route.ts의 INTERNAL_API_BASE가 /rag 없이 /api/v1을 사용해야 한다.
    """

    def _make_app(self):
        from fastapi import FastAPI
        from app.routers.tenants import router
        from app.db.session import get_db
        from app.middleware.auth import verify_admin

        app = FastAPI()
        app.include_router(router)

        async def override_db():
            db = AsyncMock()
            db.execute = AsyncMock(
                return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: []))
            )
            yield db

        async def override_admin():
            return None

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[verify_admin] = override_admin
        return app

    def test_correct_path_without_rag_prefix_returns_200(self):
        """/api/v1/tenants/ — Docker 내부 직접 호출 경로 → 200 (GREEN)"""
        client = TestClient(self._make_app())
        response = client.get("/api/v1/tenants/")
        assert response.status_code == 200

    def test_wrong_path_with_rag_prefix_returns_404(self):
        """/rag/api/v1/tenants/ — 수정 전 잘못된 경로 → 404 (RED→GREEN)

        INTERNAL_API_BASE 에 /rag가 포함된 경우 이 경로로 요청이 감.
        FastAPI는 /rag/ 접두사 라우트가 없으므로 404를 반환해야 함.
        """
        client = TestClient(self._make_app())
        response = client.get("/rag/api/v1/tenants/")
        assert response.status_code == 404

    def test_icon_upload_correct_path_reaches_endpoint(self, tmp_path):
        """/api/v1/tenants/{id}/icon — 올바른 경로로 아이콘 업로드 가능 (GREEN)"""
        tenant = make_tenant()

        from fastapi import FastAPI
        from app.routers.tenants import router
        from app.db.session import get_db
        from app.middleware.auth import verify_admin

        app = FastAPI()
        app.include_router(router)

        async def override_db():
            db = AsyncMock()
            db.get = AsyncMock(return_value=tenant)
            db.flush = AsyncMock()
            db.refresh = AsyncMock()
            db.commit = AsyncMock()
            yield db

        async def override_admin():
            return None

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[verify_admin] = override_admin

        with patch("app.routers.tenants.ICONS_DIR", tmp_path):
            client = TestClient(app)
            response = client.post(
                "/api/v1/tenants/1/icon",
                files={"file": ("test.png", png_bytes(), "image/png")},
            )
        assert response.status_code == 200

    def test_icon_upload_wrong_path_returns_404(self, tmp_path):
        """/rag/api/v1/tenants/{id}/icon — 수정 전 잘못된 경로 → 404 (RED→GREEN)"""
        tenant = make_tenant()

        from fastapi import FastAPI
        from app.routers.tenants import router
        from app.db.session import get_db
        from app.middleware.auth import verify_admin

        app = FastAPI()
        app.include_router(router)

        async def override_db():
            db = AsyncMock()
            db.get = AsyncMock(return_value=tenant)
            db.flush = AsyncMock()
            db.refresh = AsyncMock()
            db.commit = AsyncMock()
            yield db

        async def override_admin():
            return None

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[verify_admin] = override_admin

        with patch("app.routers.tenants.ICONS_DIR", tmp_path):
            client = TestClient(app)
            response = client.post(
                "/rag/api/v1/tenants/1/icon",
                files={"file": ("test.png", png_bytes(), "image/png")},
            )
        assert response.status_code == 404
