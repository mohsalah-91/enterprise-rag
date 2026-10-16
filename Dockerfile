FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

# Optional package mirror for networks that block public PyPI:
#   docker build --build-arg PIP_INDEX_URL=https://<mirror>/simple/ .
ARG PIP_INDEX_URL

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app app ./app
COPY --chown=app:app migrations ./migrations

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT', '8000'), timeout=2)"

CMD ["sh", "-c", "exec uvicorn app.main:app --host \"${HOST:-0.0.0.0}\" --port \"${PORT:-8000}\""]
