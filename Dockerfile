# 買い物リサーチ（公開Web）本番用。VPS 要件: 非root・HEALTHCHECK 内蔵・BASE_PATH 対応。
FROM python:3.12-slim

ENV PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Tokyo

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# BASE_PATH 未設定なら /healthz、設定時は ${BASE_PATH}/healthz を叩く
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,sys,urllib.request; b=os.environ.get('BASE_PATH','').rstrip('/'); sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000'+b+'/healthz', timeout=3).status==200 else 1)"

# --proxy-headers は付けない（クライアント IP は CF-Connecting-IP を自前で見る）
CMD ["uvicorn", "shopping.web:app", "--host", "0.0.0.0", "--port", "8000"]
