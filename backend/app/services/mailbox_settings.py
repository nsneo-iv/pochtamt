"""Настройки ящика, общие для админки и личного кабинета: режим, автоответ, пересылка, Sieve, BCC.

Пересылка — алиас в базе с адресом ящика (цели + сам ящик при keep_copy). Автоответ и пользовательские
правила — Sieve-скрипт «panel», который заливается через ManageSieve после каждого сохранения.
"""
import datetime as dt

import psycopg

from .. import db
from ..models import Autoreply, Forward
from . import sieve

SETTINGS_COLS = ("autoreply_enabled, autoreply_subject, autoreply_body, autoreply_from, autoreply_to, sieve_custom, "
                 "bcc_address, sieve_synced_at")


def get(address: str) -> dict:
    m = db.fetch_one("SELECT address, mode FROM mailboxes WHERE address = %s", (address,))
    if not m:
        raise KeyError(address)
    st = db.fetch_one(f"SELECT {SETTINGS_COLS} FROM mailbox_settings WHERE address = %s", (address,)) or {}
    targets = [r["target"] for r in db.fetch_all(
        "SELECT target FROM alias_targets WHERE alias = %s ORDER BY target", (address,))]
    keep = address in targets
    return {
        "address": address, "mode": m["mode"],
        "autoreply": Autoreply(enabled=st.get("autoreply_enabled", False), subject=st.get("autoreply_subject", ""),
                               body=st.get("autoreply_body", ""), date_from=st.get("autoreply_from"),
                               date_to=st.get("autoreply_to")),
        "forward": Forward(targets=[t for t in targets if t != address], keep_copy=keep if targets else True),
        "sieve_custom": st.get("sieve_custom", ""), "bcc_address": st.get("bcc_address"),
        "sieve_synced_at": st.get("sieve_synced_at"),
    }


def _ensure_row(conn: psycopg.Connection, address: str) -> None:
    conn.execute("INSERT INTO mailbox_settings (address) VALUES (%s) ON CONFLICT (address) DO NOTHING", (address,))


def save_autoreply(conn: psycopg.Connection, address: str, a: Autoreply) -> None:
    if a.date_from and a.date_to and a.date_from > a.date_to:
        raise ValueError("дата окончания автоответа раньше даты начала")
    _ensure_row(conn, address)
    conn.execute(
        "UPDATE mailbox_settings SET autoreply_enabled = %s, autoreply_subject = %s, autoreply_body = %s,"
        " autoreply_from = %s, autoreply_to = %s WHERE address = %s",
        (a.enabled, a.subject, a.body, a.date_from, a.date_to, address))


def save_sieve_custom(conn: psycopg.Connection, address: str, text: str) -> None:
    _ensure_row(conn, address)
    conn.execute("UPDATE mailbox_settings SET sieve_custom = %s WHERE address = %s", (text, address))


def save_bcc(conn: psycopg.Connection, address: str, bcc: str | None) -> None:
    _ensure_row(conn, address)
    conn.execute("UPDATE mailbox_settings SET bcc_address = %s WHERE address = %s", (bcc, address))


def save_forward(conn: psycopg.Connection, address: str, f: Forward) -> None:
    """Пересылка = алиас с адресом ящика. Без целей — алиас удаляется."""
    domain = address.rpartition("@")[2]
    targets = [t for t in f.targets if t != address]
    conn.execute("DELETE FROM aliases WHERE address = %s", (address,))
    if not targets:
        return
    if f.keep_copy:
        targets.append(address)
    conn.execute("INSERT INTO aliases (address, domain, description, active) VALUES (%s, %s, %s, true)",
                 (address, domain, "пересылка ящика"))
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO alias_targets (alias, target) VALUES (%s, %s)", [(address, t) for t in targets])


def sync_sieve(address: str) -> str | None:
    """Собрать скрипт из базы и залить. Возвращает None или текст ошибки (сохраняется в ответе, не ломает запрос)."""
    st = db.fetch_one(f"SELECT {SETTINGS_COLS} FROM mailbox_settings WHERE address = %s", (address,))
    script = sieve.build_script(st or {})
    try:
        sieve.upload(address, script)
    except sieve.SieveError as e:
        return str(e)
    with db.tx() as conn:
        _ensure_row(conn, address)
        conn.execute("UPDATE mailbox_settings SET sieve_synced_at = %s WHERE address = %s",
                     (dt.datetime.now(dt.timezone.utc), address))
    return None


def check_custom(address: str, text: str) -> str | None:
    """Проверить пользовательские правила в составе полного скрипта."""
    st = dict(db.fetch_one(f"SELECT {SETTINGS_COLS} FROM mailbox_settings WHERE address = %s", (address,)) or {})
    st["sieve_custom"] = text
    try:
        return sieve.check(address, sieve.build_script(st))
    except sieve.SieveError as e:
        return str(e)
