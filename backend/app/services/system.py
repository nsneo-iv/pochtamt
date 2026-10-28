"""Состояние сервера: метрики хоста от агента + база, Redis, Rspamd; выборки в system_samples для графиков."""
import datetime as dt
import socket

import redis

from .. import db
from ..config import settings
from . import agent, rspamd


def _redis_info() -> dict | None:
    try:
        r = redis.Redis.from_url(settings.redis_url, socket_timeout=3)
        info = r.info()
        return {"used_memory": info.get("used_memory", 0), "keys": sum(
            v.get("keys", 0) for k, v in info.items() if k.startswith("db") and isinstance(v, dict)),
            "uptime_s": info.get("uptime_in_seconds", 0)}
    except redis.RedisError:
        return None


def _db_info() -> dict:
    row = db.fetch_one("SELECT pg_database_size(current_database()) AS size, "
                       "(SELECT count(*) FROM mailboxes) AS mailboxes, "
                       "(SELECT COALESCE(sum(messages), 0) FROM mailbox_usage) AS messages")
    return {"size_bytes": int(row["size"]), "mailboxes": row["mailboxes"], "messages_total": int(row["messages"])}


def overview() -> dict:
    out = {"host": None, "services": {}, "queue": {}, "sessions": {}, "mail": {}, "cert": {}, "fail2ban": {},
           "db": _db_info(), "redis": _redis_info(), "rspamd": rspamd.stat(), "agent_ok": True}
    try:
        s = agent.system()
    except agent.AgentError as e:
        out["agent_ok"] = False
        out["detail"] = str(e)
        return out
    out["host"] = {"hostname": socket.gethostname(), "uptime_s": s["uptime_s"], "load": s["load"],
                   "cpu_count": s["cpu_count"], "cpu_percent": s["cpu_percent"], "mem": s["mem"], "disks": s["disks"]}
    for k in ("services", "queue", "sessions", "mail", "cert", "fail2ban"):
        out[k] = s.get(k, {})
    return out


def sample() -> bool:
    """Записать выборку в system_samples (таймер). False — агент недоступен."""
    try:
        s = agent.system()
    except agent.AgentError:
        return False
    # агент считает почту за 24 ч; в выборку пишем среднее за час
    m = s.get("mail", {})
    hours = max(1, m.get("hours", 24))
    rs = rspamd.stat() or {}
    disks = {d["mount"]: d for d in s.get("disks", [])}
    root = disks.get("/", {"used": 0, "total": 0})
    vmail = disks.get("/var/vmail", root)
    with db.tx() as conn:
        conn.execute(
            "INSERT INTO system_samples (load1, cpu_percent, mem_used, mem_total, disk_used, disk_total, vmail_used,"
            " vmail_total, queue_active, queue_deferred, sessions_imap, delivered_1h, sent_out_1h, bounced_1h,"
            " deferred_1h, rejected_1h, rspamd_scanned, rspamd_spam)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (s["load"][0], s["cpu_percent"], s["mem"]["used"], s["mem"]["total"], root["used"], root["total"],
             vmail["used"], vmail["total"], s["queue"].get("active", 0), s["queue"].get("deferred", 0),
             s["sessions"].get("imap", 0), round(m.get("delivered", 0) / hours), round(m.get("sent_out", 0) / hours),
             round(m.get("bounced", 0) / hours), round(m.get("deferred", 0) / hours), round(m.get("rejected", 0) / hours),
             rs.get("scanned", 0), rs.get("spam", 0)))
        conn.execute("DELETE FROM system_samples WHERE ts < now() - interval '30 days'")
    return True


def history(hours: int) -> list[dict]:
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    return db.fetch_all("SELECT * FROM system_samples WHERE ts >= %s ORDER BY ts", (since,))
