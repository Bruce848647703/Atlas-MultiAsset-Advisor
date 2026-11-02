# Atlas Multi-Asset Advisor — runtime image.
#
# Build:  docker build -t atlas-multiasset-advisor .
# Run:    docker run --rm -p 127.0.0.1:8501:8501 \
#           -e ATLAS_ACCESS_TOKEN='choose-a-long-secret' atlas-multiasset-advisor
#
# The image runs as a non-root user and refuses to start without an access
# token unless ATLAS_ALLOW_INSECURE=1 is set explicitly.

FROM python:3.13-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai \
    PORT=8501

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first so code edits do not invalidate the wheel layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --uid 10001 atlas \
    && mkdir -p /app/data /app/data_cache /app/examples/demo_outputs \
    && chown -R atlas:atlas /app/data /app/data_cache /app/examples/demo_outputs \
    && chmod +x /app/deploy/docker-entrypoint.sh

USER atlas

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4).getcode() == 200 else 1)"

ENTRYPOINT ["/app/deploy/docker-entrypoint.sh"]