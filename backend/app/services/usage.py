"""Занятое место ящиков: берём у агента (doveadm quota) и пишем в mailbox_usage."""
from .. import db
from . import agent


def sync() -> int:
    rows = agent.quota()
    with db.tx() as conn, conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO mailbox_usage (address, bytes, messages, updated_at) "
            "SELECT %s, %s, %s, now() WHERE EXISTS (SELECT 1 FROM mailboxes WHERE address = %s) "
            "ON CONFLICT (address) DO UPDATE SET bytes = EXCLUDED.bytes, messages = EXCLUDED.messages, "
            "updated_at = now()",
            [(r["address"], r["bytes"], r["messages"], r["address"]) for r in rows])
    return len(rows)
