#!/usr/bin/env sh
# Container entrypoint.
#
# Platforms-as-a-service inject the port to listen on and expect the process to
# come up ready. This does the one-time setup (tables plus the source catalog)
# and then hands over to uvicorn.
set -e

PORT="${PORT:-${DRAKEN_PORT:-8000}}"

echo "[draken] preparing the database and source catalog..."
python -m draken.cli.main init-db >/dev/null 2>&1 || {
    echo "[draken] init-db failed; the database may be unreachable" >&2
    exit 1
}

if [ "${DRAKEN_AUTH_ENABLED}" = "true" ] \
   && [ -z "${DRAKEN_ADMIN_PASSWORD}" ] \
   && [ -z "${DRAKEN_ADMIN_PASSWORD_HASH}" ]; then
    echo "[draken] WARNING: auth is enabled but no password is set." >&2
    echo "[draken] Set DRAKEN_ADMIN_PASSWORD (or DRAKEN_ADMIN_PASSWORD_HASH) or nobody can sign in." >&2
fi

if [ "${DRAKEN_AUTH_ENABLED}" != "true" ]; then
    echo "[draken] NOTICE: authentication is OFF. Anyone who reaches this URL gets in." >&2
    echo "[draken] Set DRAKEN_AUTH_ENABLED=true and DRAKEN_ADMIN_PASSWORD before sharing it." >&2
fi

echo "[draken] listening on 0.0.0.0:${PORT}"
exec uvicorn draken.api.app:app \
    --host 0.0.0.0 --port "${PORT}" \
    --proxy-headers --forwarded-allow-ips='*'
