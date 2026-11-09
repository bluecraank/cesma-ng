#!/bin/sh
set -e
# Apply database migrations before the API starts (only one container should do this).
if [ "${CESMA_RUN_MIGRATIONS:-true}" = "true" ]; then
  alembic upgrade head
fi
exec "$@"
