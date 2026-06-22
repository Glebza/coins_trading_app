"""PostgreSQL connection helpers for transition_service."""

from __future__ import annotations

import os

import psycopg2


def connect(*, database_url: str, schema: str):
    connection = psycopg2.connect(database_url)
    with connection.cursor() as cur:
        cur.execute("SET search_path TO %s", (schema,))
    connection.commit()
    return connection
