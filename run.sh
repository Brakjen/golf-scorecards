#!/bin/sh
set -e

# If a replica exists and the local DB doesn't, restore from backup.
if [ ! -f /data/golf_scorecards.db ]; then
  echo "No local database found — attempting restore from Litestream replica…"
  litestream restore -if-replica-exists -config /app/litestream.yml /data/golf_scorecards.db
fi

# Start the app under Litestream (continuous replication).
exec litestream replicate -config /app/litestream.yml -exec \
  "uvicorn golf_scorecards.main:app --host 0.0.0.0 --port 8080 --proxy-headers --forwarded-allow-ips '*'"
