# RAG Chatbot Platform

멀티테넌트 RAG(Retrieval-Augmented Generation) 챗봇 플랫폼. 웹사이트에 임베드 가능한 위젯과 관리자 대시보드를 제공한다.

## 아키텍처 개요

```
┌─────────────┐     ┌──────────────────────────────────────┐
│   Browser   │────▶│  Nginx :3000                         │
└─────────────┘     │  /rag/api/*   → FastAPI :8000        │
                    │  /rag/admin/* → Next.js :3001         │
                    │  /rag/widget/ → FastAPI static        │
                    └──────────────────────────────────────┘
                              │
               ┌──────────────┴──────────────┐
               ▼                             ▼
        FastAPI (Python)              Next.js (TypeScript)
        apps/api/                     apps/admin/
               │
        ┌──────┴──────┐
        ▼             ▼
  PostgreSQL       Redis
  (pgvector)    (세션/캐시)
```

## 디렉터리 구조

```
rag/
├── apps/
│   ├── api/                    # FastAPI 백엔드
│   │   ├── app/
│   │   │   ├── config.py       # pydantic-settings 환경변수
│   │   │   ├── main.py         # FastAPI 앱 진입점
│   │   │   ├── db/             # SQLAlchemy 세션/base
│   │   │   ├── models/         # ORM 모델
│   │   │   │   ├── tenant.py   # 테넌트 (api_key, widget_config, lang_policy)
│   │   │   │   ├── document.py # 인제스트된 문서
│   │   │   │   ├── chunk.py    # 벡터 청크 (pgvector)
│   │   │   │   └── conversation.py  # 대화/메시지
│   │   │   ├── routers/        # API 엔드포인트
│   │   │   │   ├── ingest.py   # 문서/URL 인제스트
│   │   │   │   ├── chat.py     # SSE 스트리밍 채팅
│   │   │   │   ├── analytics.py # 통계/대화 조회
│   │   │   │   └── tenants.py  # 테넌트 CRUD
│   │   │   ├── services/       # 비즈니스 로직
│   │   │   │   ├── rag.py      # RAG 검색 + 프롬프트 빌드
│   │   │   │   ├── ingest.py   # 파이프라인 조율
│   │   │   │   ├── embeddings.py # OpenAI-compatible 임베딩
│   │   │   │   ├── llm.py      # OpenAI-compatible LLM
│   │   │   │   ├── chunker.py  # 텍스트 청킹
│   │   │   │   ├── parser.py   # PDF/DOCX/TXT 파싱
│   │   │   │   ├── crawler.py  # Playwright 웹 크롤러
│   │   │   │   ├── language.py # Accept-Language 파싱/해석
│   │   │   │   └── domain_validation.py # 도메인 화이트리스트
│   │   │   └── middleware/
│   │   │       └── auth.py     # X-API-Key 헤더 인증
│   │   ├── alembic/            # DB 마이그레이션
│   │   └── tests/unit/         # pytest 단위 테스트
│   ├── admin/                  # Next.js 관리자 UI
│   │   └── src/
│   │       ├── app/            # Next.js App Router
│   │       ├── components/     # 대시보드 패널들
│   │       └── lib/api.ts      # API 클라이언트
│   └── widget/
│       └── chatbot.js          # 임베드용 Vanilla JS (Shadow DOM)
├── nginx/nginx.conf            # 리버스 프록시 설정
├── docker-compose.yml          # 전체 스택 구성
└── .env.example                # 환경변수 템플릿
```

## 실행 방법

### 1. 환경변수 설정

```bash
cp .env.example .env
# .env 편집: LLM_BASE_URL, EMBEDDING_BASE_URL, SECRET_KEY, ADMIN_PASSWORD 등
```

### 2. Docker Compose로 전체 스택 실행

```bash
docker compose up -d
```

서비스별 포트:
- `http://localhost:3000` — Nginx (통합 진입점)
- `http://localhost:3000/rag/admin/` — 관리자 대시보드
- `http://localhost:3000/rag/docs` — FastAPI Swagger UI
- `http://localhost:8000` — FastAPI 직접 접근 (개발용)
- `http://localhost:3001` — Next.js 직접 접근 (개발용)

### 3. DB 마이그레이션

```bash
docker compose exec api alembic upgrade head
```

### 4. 로컬 개발 (API만)

```bash
cd apps/api
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## 핵심 개념

### 멀티테넌시

- 모든 API 요청은 `X-API-Key` 헤더로 테넌트를 식별
- 테넌트마다 문서, 대화, 위젯 설정이 독립적으로 분리
- 관리자는 Basic Auth (`ADMIN_USERNAME` / `ADMIN_PASSWORD`) 사용

### 인제스트 파이프라인

```
URL/파일 업로드
    → 파싱 (PDF/DOCX/TXT/웹)
    → 청킹 (tiktoken 기반 토큰 크기)
    → 임베딩 (OpenAI-compatible API)
    → PostgreSQL pgvector 저장
```

비동기 백그라운드 태스크로 처리 (`BackgroundTasks`).

### RAG 채팅 흐름

```
사용자 메시지
    → 도메인 화이트리스트 검증
    → Accept-Language 파싱 → 언어 정책 적용
    → 임베딩 → pgvector 코사인 유사도 검색 (top_k=5)
    → 시스템 프롬프트 + 컨텍스트 + 히스토리 구성
    → LLM 스트리밍 응답 (SSE)
    → 대화 DB 저장
```

### 위젯 임베드

```html
<script>
  window.RagChatConfig = {
    apiKey: "tenant_xxxxx",
    apiUrl: "https://your-domain.com/rag/api/v1/chat"
  };
</script>
<script src="https://your-domain.com/rag/widget/chatbot.js" defer></script>
```

Shadow DOM으로 호스트 페이지 스타일과 완전 격리.

## 환경변수 요약

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `LLM_BASE_URL` | OpenAI-compatible LLM API URL | `http://localhost:11434/v1` |
| `LLM_MODEL` | 사용할 LLM 모델명 | `llama3.2:3b` |
| `EMBEDDING_BASE_URL` | 임베딩 API URL | `http://localhost:11434/v1` |
| `EMBEDDING_MODEL` | 임베딩 모델명 | `nomic-embed-text` |
| `EMBEDDING_DIMENSION` | 임베딩 벡터 차원 | `768` |
| `DATABASE_URL` | PostgreSQL 연결 URL | — |
| `REDIS_URL` | Redis 연결 URL | `redis://localhost:6379` |
| `SECRET_KEY` | 앱 시크릿 키 (32자 이상) | — |
| `ADMIN_USERNAME` | 관리자 로그인 ID | `admin` |
| `ADMIN_PASSWORD` | 관리자 로그인 PW | — |
| `APP_PREFIX` | API 경로 prefix | `/rag` |
| `DEFAULT_LANGUAGE` | 기본 언어 | `ko` |
| `MAX_UPLOAD_SIZE_MB` | 업로드 최대 크기 | `50` |

Docker Compose 내부에서는 `host.docker.internal`로 로컬 Ollama/LM Studio에 접근.

## 기술 스택

**Backend**
- Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Alembic
- PostgreSQL 16 + pgvector, Redis 7
- OpenAI SDK (Ollama / LM Studio / vLLM 등 호환 엔드포인트 사용)
- Playwright (웹 크롤링), pypdf, python-docx

**Frontend**
- Next.js (App Router), TypeScript
- CSS Modules

**Infra**
- Docker Compose, Nginx (리버스 프록시 + SSE 스트리밍 설정)

## 테스트

```bash
cd apps/api
pytest tests/ -v --cov=app
```

테스트 위치: `apps/api/tests/unit/`
- `test_chunker.py` — 청킹 로직
- `test_language.py` — 언어 감지/해석
- `test_domain_validation.py` — 도메인 화이트리스트

## 주요 API 엔드포인트

모든 엔드포인트는 `X-API-Key` 헤더 필요 (테넌트 관리 API 제외).

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/rag/api/v1/ingest/url` | URL 인제스트 (비동기) |
| `POST` | `/rag/api/v1/ingest/file` | 파일 업로드 인제스트 (비동기) |
| `GET` | `/rag/api/v1/ingest/documents` | 문서 목록 조회 |
| `DELETE` | `/rag/api/v1/ingest/documents/{id}` | 문서 삭제 |
| `POST` | `/rag/api/v1/chat` | SSE 스트리밍 채팅 |
| `GET` | `/rag/api/v1/analytics/stats` | 테넌트 통계 |
| `GET` | `/rag/api/v1/analytics/conversations` | 대화 목록 |
| `GET` | `/rag/api/v1/analytics/conversations/{session_id}/messages` | 대화 메시지 |

SSE 이벤트 타입: `session` → `sources` → `token` (반복) → `done`
