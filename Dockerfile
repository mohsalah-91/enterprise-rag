FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MCP_HOST=0.0.0.0 \
    MCP_SERVER_PORT=8765

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

# Optional package mirror for networks that block public PyPI:
#   docker build --build-arg PIP_INDEX_URL=https://<mirror>/simple/ .
ARG PIP_INDEX_URL

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app app ./app
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app mcp_server.py ./

USER app

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import os, socket; socket.create_connection(('127.0.0.1', int(os.environ.get('MCP_SERVER_PORT', '8765'))), 2).close()"

CMD ["python", "mcp_server.py"]
