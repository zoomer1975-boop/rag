"""테스트 고정장치 (fixtures)"""

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app


# 테스트용 SQLite DB
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    """비동기 엔진 고정장치"""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True,
        connect_args={"check_same_thread": False},
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """비동기 DB 세션 고정장치"""
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, future=True
    )

    async with async_session() as session:
        yield session


@pytest.fixture
def app_instance():
    """FastAPI 앱 고정장치"""
    return app


@pytest_asyncio.fixture
async def client(
    app_instance, db_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    """비동기 HTTP 클라이언트 고정장치"""

    async def override_get_db():
        yield db_session

    app_instance.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(app=app_instance, base_url="http://test") as test_client:
        yield test_client

    app_instance.dependency_overrides.clear()


@pytest_asyncio.fixture
async def setup_test_db(db_session: AsyncSession):
    """테스트 DB 설정 고정장치"""
    # 테스트 전에 DB를 정리해야 할 경우 여기서 처리
    yield
    # 테스트 후 정리 로직
