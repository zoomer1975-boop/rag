FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성 + Playwright chromium 의존 라이브러리
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright 브라우저 설치 (크롤러용) - 폰트 패키지 제외
RUN playwright install chromium

COPY . .

# 업로드 디렉토리 생성
RUN mkdir -p /app/uploads /app/widget_dist

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
