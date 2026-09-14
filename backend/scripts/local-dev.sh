#!/bin/bash
set -euo pipefail

# Make sure hex is installed
mix local.hex --force && mix local.rebar --force

# Get deps
mix deps.get

# Postgres must be on the compose network (hostname "postgres") before ecto runs.
# nxdomain = the postgres container is not running / not attached.
echo "Waiting for postgres DNS + port..."
i=0
until getent hosts postgres >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -gt 60 ]; then
    echo "postgres hostname never appeared. Is the postgres service up? Try: docker compose logs postgres" >&2
    exit 1
  fi
  sleep 2
done

# Do any DB migration (ecto.create is ok if the DB already exists)
mix ecto.setup

# Start the server
exec mix phx.server
