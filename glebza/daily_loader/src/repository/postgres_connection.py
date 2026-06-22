"""PostgreSQL connection helper for daily_loader repositories."""

from __future__ import annotations

import os

import psycopg2


def connect():
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise ValueError("DATABASE_URL is required")

    schema = os.environ.get("DATABASE_DEFAULT_SCHEMA", "backtests").strip() or "backtests"
    connection = psycopg2.connect(database_url)
    with connection.cursor() as cur:
        cur.execute("SET search_path TO %s", (schema,))
    connection.commit()
    return connection
