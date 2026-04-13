FROM python:3.11-slim

WORKDIR /app

# PostgreSQL 연결을 위한 시스템 의존성 설치
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 패키징 최적화를 위해 의존성 먼저 복사
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 업로드 디렉토리 생성
RUN mkdir -p /app/uploads /app/widget_dist

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
