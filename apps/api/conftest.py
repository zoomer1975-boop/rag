"""Pytest 설정"""

import sys
from pathlib import Path

# 앱 경로 추가
sys.path.insert(0, str(Path(__file__).parent))

# SQLite 호환성을 위해 JSONB를 JSON으로 치환
from sqlalchemy import JSON, TypeDecorator
from sqlalchemy.dialects import postgresql

class JSONBCompat(TypeDecorator):
    """SQLite 호환 JSONB 타입"""
    impl = JSON
    cache_ok = True

# 모든 모델이 로드되기 전에 JSONB를 대체
postgresql.JSONB = JSONBCompat
postgresql.json.JSONB = JSONBCompat

pytest_plugins = ["tests.fixtures"]
