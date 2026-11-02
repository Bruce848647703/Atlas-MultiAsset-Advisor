#!/bin/sh
# Container entrypoint: fail closed when no access token is configured.
set -eu

if [ -z "${ATLAS_ACCESS_TOKEN:-}" ]; then
    if [ "${ATLAS_ALLOW_INSECURE:-0}" != "1" ]; then
        echo "error: ATLAS_ACCESS_TOKEN is required." >&2
        echo "       Set it with -e ATLAS_ACCESS_TOKEN='...' (or ATLAS_ALLOW_INSECURE=1 for a local-only demo)." >&2
        exit 1
    fi
    echo "warning: ATLAS_ACCESS_TOKEN is empty; starting without an access gate (ATLAS_ALLOW_INSECURE=1)." >&2
fi

exec streamlit run dashboard/app.py \
    --server.address 0.0.0.0 \
    --server.port "${PORT:-8501}" \
    --server.headless true