"""Журнал действий: каждая мутация через API пишет строку в audit_log."""
import json
from typing import Any

import psycopg


def log(conn: psycopg.Connection, actor: str, action: str, obj: str, details: dict[str, Any] | None = None,
        ip: str | None = None) -> None:
    conn.execute(
        "INSERT INTO audit_log (actor, action, object, details, ip) VALUES (%s, %s, %s, %s::jsonb, %s)",
        (actor, action, obj, json.dumps(details or {}, ensure_ascii=False, default=str), ip),
    )
