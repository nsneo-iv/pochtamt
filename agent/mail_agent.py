#!/usr/bin/env python3
"""Агент на почтовом хосте: единственная точка, где панель касается самого сервера.

Слушает только 127.0.0.1:8025, требует заголовок X-Agent-Token (AGENT_TOKEN из agent/.env),
умеет ровно четыре вещи и ничего больше:

    GET    /queue        — очередь Postfix (postqueue -j)
    POST   /queue/flush  — повторить доставку всей очереди (postqueue -f)
    DELETE /queue/<id>   — удалить письмо из очереди (postsuper -d <id>)
    GET    /quota        — занятое место всех ящиков (doveadm quota get -A)
    GET    /antivirus    — версия ClamAV и баз (clamdscan --version, без sudo: mailagent в группе clamav)
    POST   /antivirus/update — внеплановая проверка баз (systemctl restart clamav-freshclam)
    GET    /settings     — глобальные параметры Postfix/Dovecot из реестра (apply_settings.py get)
    GET    /system       — нагрузка и состояние хоста: CPU, память, диски, службы, очередь, сессии IMAP,
                           сертификат, баны fail2ban, почта за сутки по логу Postfix
    POST   /settings/<service>/<key> {"value": ...} — изменить параметр (apply_settings.py set …)

Команды выполняются через sudo по белому списку (install/sudoers-mail-agent). Никакого шелла, никаких
параметров от клиента, кроме id письма, который проверяется регуляркой. Пять команд, см. sudoers.
Запуск: systemd-служба mail-agent (install/mail-agent.service), без зависимостей кроме Python 3.
"""
import hmac
import json
import os
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE_ID_RE = re.compile(r"^[A-Z0-9]{6,20}$")

SUDO = "/usr/bin/sudo"
CMD_QUEUE = [SUDO, "-n", "/usr/sbin/postqueue", "-j"]
CMD_FLUSH = [SUDO, "-n", "/usr/sbin/postqueue", "-f"]
CMD_DELETE = [SUDO, "-n", "/usr/sbin/postsuper", "-d"]
CMD_QUOTA = [SUDO, "-n", "/usr/bin/doveadm", "-f", "tab", "quota", "get", "-A"]
CMD_AV_VERSION = ["/usr/bin/clamdscan", "--version"]
CMD_AV_SIGS = ["/usr/bin/sigtool", "--info", "/var/lib/clamav/daily.cvd"]
CMD_AV_ACTIVE = ["/usr/bin/systemctl", "is-active", "clamav-daemon"]
CMD_AV_UPDATE = [SUDO, "-n", "/usr/bin/systemctl", "restart", "clamav-freshclam"]
CMD_SETTINGS = [SUDO, "-n", "/opt/mail-agent/apply_settings.py"]   # сам проверяет ключи и значения
CMD_WHO = [SUDO, "-n", "/usr/bin/doveadm", "-f", "tab", "who"]
CMD_F2B_LIST = [SUDO, "-n", "/usr/bin/fail2ban-client", "status"]
CMD_F2B_JAIL = [SUDO, "-n", "/usr/bin/fail2ban-client", "status"]          # + имя jail
CMD_LOG_TAIL = [SUDO, "-n", "/usr/bin/tail", "-c", "20000000", "/var/log/postfix.log"]
SERVICES = ["postfix", "dovecot", "rspamd", "clamav-daemon", "clamav-freshclam", "redis-server", "postgresql",
            "nginx", "unbound", "fail2ban", "nftables", "mail-backend", "mail-agent"]
CERT_PATH = "/etc/ssl/mail/fullchain.pem"
MOUNTS = ["/", "/var/vmail"]
KEY_RE = re.compile(r"^[a-z_]{3,64}$")


def load_env() -> dict:
    """agent/.env или /etc/mail-agent.env: KEY=VALUE, переменные окружения имеют приоритет."""
    env = {}
    for path in (os.path.join(HERE, ".env"), "/etc/mail-agent.env"):
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        env[k.strip()] = v.strip().strip("\"'")
            break
    env.update({k: v for k, v in os.environ.items() if k in ("AGENT_TOKEN", "AGENT_LISTEN")})
    return env


ENV = load_env()
TOKEN = ENV.get("AGENT_TOKEN", "")
HOST, _, PORT = ENV.get("AGENT_LISTEN", "127.0.0.1:8025").rpartition(":")


def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout).strip()[:500])
    return p.stdout


def parse_queue(out: str) -> list[dict]:
    """postqueue -j печатает по одному JSON-объекту на строку."""
    items = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        j = json.loads(line)
        rcpts = j.get("recipients", [])
        items.append({
            "id": j.get("queue_id", ""),
            "sender": j.get("sender", ""),
            "recipients": [r.get("address", "") for r in rcpts],
            "size": int(j.get("message_size", 0)),
            "arrival": int(j.get("arrival_time", 0)),
            "queue": j.get("queue_name", ""),
            "reason": next((r.get("delay_reason", "") for r in rcpts if r.get("delay_reason")), ""),
        })
    return items


def parse_quota(out: str) -> list[dict]:
    """doveadm -f tab quota get -A: Username  Type  Name  Value  Limit  %  (Value для STORAGE — в килобайтах)."""
    rows: dict[str, dict] = {}
    lines = out.splitlines()
    if not lines:
        return []
    header = [h.strip().lower() for h in lines[0].split("\t")]
    for line in lines[1:]:
        if not line.strip():
            continue
        cols = dict(zip(header, line.split("\t")))
        user = cols.get("username", "")
        if not user:
            continue
        rec = rows.setdefault(user, {"address": user, "bytes": 0, "messages": 0})
        typ = cols.get("type", "").upper()
        try:
            val = int(cols.get("value", "0"))
        except ValueError:
            val = 0
        if typ == "STORAGE":
            rec["bytes"] = val * 1024
        elif typ == "MESSAGE":
            rec["messages"] = val
    return list(rows.values())


def antivirus_info() -> dict:
    """ClamAV 1.4.3/28149/Sat Oct 10 06:24:04 2026 -> движок, версия баз, дата; sigtool даёт число сигнатур."""
    info = {"available": False, "daemon_active": False, "engine_version": None, "db_version": None,
            "db_date": None, "signatures": None}
    p = subprocess.run(CMD_AV_ACTIVE, capture_output=True, text=True, timeout=10)
    info["daemon_active"] = p.stdout.strip() == "active"
    try:
        ver = run(CMD_AV_VERSION).strip()           # падает, если clamd не отвечает по сокету
        parts = ver.replace("ClamAV ", "").split("/")
        info["available"] = True
        info["engine_version"] = parts[0] if parts else ver
        if len(parts) >= 3:
            info["db_version"], info["db_date"] = parts[1], parts[2]
    except RuntimeError as e:
        info["detail"] = str(e)[:200]
    try:
        for line in run(CMD_AV_SIGS).splitlines():
            if line.startswith("Signatures:"):
                info["signatures"] = int(line.split(":")[1])
    except (RuntimeError, ValueError):
        pass
    return info


# ---------------------------------------------------------------- состояние хоста ----
def _cpu_times() -> tuple[int, int]:
    with open("/proc/stat") as f:
        parts = f.readline().split()[1:]
    vals = [int(x) for x in parts]
    idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
    return sum(vals), idle


def cpu_percent(interval: float = 0.5) -> float:
    import time
    t1, i1 = _cpu_times()
    time.sleep(interval)
    t2, i2 = _cpu_times()
    dt_ = t2 - t1
    return round(100.0 * (1 - (i2 - i1) / dt_), 1) if dt_ else 0.0


def meminfo() -> dict:
    m = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, _, v = line.partition(":")
            m[k] = int(v.split()[0]) * 1024
    return {"total": m.get("MemTotal", 0), "available": m.get("MemAvailable", 0),
            "used": m.get("MemTotal", 0) - m.get("MemAvailable", 0),
            "swap_total": m.get("SwapTotal", 0), "swap_used": m.get("SwapTotal", 0) - m.get("SwapFree", 0)}


def disks() -> list[dict]:
    out, seen = [], set()
    for mnt in MOUNTS:
        try:
            st = os.statvfs(mnt)
        except OSError:
            continue
        key = (st.f_fsid if hasattr(st, "f_fsid") else 0, st.f_blocks)
        if key in seen:
            continue        # /var/vmail на том же разделе, что / — не дублируем
        seen.add(key)
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        out.append({"mount": mnt, "total": total, "used": total - free, "free": free})
    return out


def services_state() -> dict:
    p = subprocess.run(["/usr/bin/systemctl", "is-active"] + SERVICES, capture_output=True, text=True, timeout=15)
    states = p.stdout.split()
    return {s: (states[i] if i < len(states) else "unknown") for i, s in enumerate(SERVICES)}


def queue_counts() -> dict:
    counts = {"active": 0, "deferred": 0, "hold": 0, "incoming": 0, "maildrop": 0, "total": 0}
    try:
        for item in parse_queue(run(CMD_QUEUE)):
            q = item.get("queue", "")
            counts[q] = counts.get(q, 0) + 1
            counts["total"] += 1
    except RuntimeError:
        pass
    return counts


def sessions() -> dict:
    """doveadm -f tab who: username  #  proto  (pids)  (ips)."""
    out = {"imap": 0, "users": 0, "by_proto": {}}
    try:
        lines = run(CMD_WHO).splitlines()[1:]
    except RuntimeError:
        return out
    users = set()
    for line in lines:
        cols = line.split("\t")
        if len(cols) < 3:
            continue
        try:
            n = int(cols[1])
        except ValueError:
            n = 1
        proto = cols[2]
        out["by_proto"][proto] = out["by_proto"].get(proto, 0) + n
        users.add(cols[0])
    out["imap"] = out["by_proto"].get("imap", 0)
    out["users"] = len(users)
    return out


def cert_info() -> dict:
    try:
        p = subprocess.run(["/usr/bin/openssl", "x509", "-in", CERT_PATH, "-noout", "-enddate", "-subject"],
                           capture_output=True, text=True, timeout=10)
        import datetime as _dt
        info = {}
        for line in p.stdout.splitlines():
            if line.startswith("notAfter="):
                na = _dt.datetime.strptime(line[9:].strip(), "%b %d %H:%M:%S %Y %Z").replace(tzinfo=_dt.timezone.utc)
                info["not_after"] = na.isoformat()
                info["days_left"] = (na - _dt.datetime.now(_dt.timezone.utc)).days
            elif line.startswith("subject="):
                info["subject"] = line[8:].strip()
        return info
    except (OSError, ValueError):
        return {}


def fail2ban() -> dict:
    out = {}
    try:
        text = run(CMD_F2B_LIST)
    except RuntimeError:
        return out
    jails = []
    for line in text.splitlines():
        if "Jail list:" in line:
            jails = [j.strip() for j in line.split(":", 1)[1].split(",") if j.strip()]
    for j in jails:
        if not re.fullmatch(r"[a-z0-9-]+", j):
            continue
        try:
            t = run(CMD_F2B_JAIL + [j])
        except RuntimeError:
            continue
        cur = tot = 0
        for line in t.splitlines():
            if "Currently banned:" in line:
                cur = int(line.split(":")[-1].strip() or 0)
            elif "Total banned:" in line:
                tot = int(line.split(":")[-1].strip() or 0)
        out[j] = {"banned": cur, "total": tot}
    return out


LOG_TS = re.compile(r"^(\w{3}) +(\d{1,2}) (\d{2}):(\d{2}):(\d{2}) ")
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def mail_stats(hours: int = 24) -> dict:
    """Счётчики по хвосту /var/log/postfix.log за последние hours часов."""
    import datetime as _dt
    stats = {"delivered": 0, "sent_out": 0, "bounced": 0, "deferred": 0, "rejected": 0, "hours": hours}
    try:
        text = run(CMD_LOG_TAIL)
    except RuntimeError:
        return stats
    now = _dt.datetime.now()
    since = now - _dt.timedelta(hours=hours)
    for line in text.splitlines():
        m = LOG_TS.match(line)
        if not m:
            continue
        try:
            ts = _dt.datetime(now.year, MONTHS.get(m.group(1), 1), int(m.group(2)), int(m.group(3)), int(m.group(4)),
                              int(m.group(5)))
        except ValueError:
            continue
        if ts > now + _dt.timedelta(days=1):
            ts = ts.replace(year=now.year - 1)
        if ts < since:
            continue
        if "status=sent" in line:
            if "dovecot-lmtp" in line:
                stats["delivered"] += 1
            else:
                stats["sent_out"] += 1
        elif "status=bounced" in line:
            stats["bounced"] += 1
        elif "status=deferred" in line:
            stats["deferred"] += 1
        elif "NOQUEUE: reject" in line or ": reject:" in line:
            stats["rejected"] += 1
    return stats


def system_info() -> dict:
    with open("/proc/uptime") as f:
        uptime = float(f.read().split()[0])
    return {
        "uptime_s": int(uptime), "load": [round(x, 2) for x in os.getloadavg()], "cpu_count": os.cpu_count() or 1,
        "cpu_percent": cpu_percent(), "mem": meminfo(), "disks": disks(), "services": services_state(),
        "queue": queue_counts(), "sessions": sessions(), "cert": cert_info(), "fail2ban": fail2ban(),
        "mail": mail_stats(),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "mail-agent/0.1"

    def log_message(self, fmt, *args):  # в journal только ошибки и мутации
        if self.command != "GET":
            sys.stderr.write("%s %s\n" % (self.command, self.path))

    def _auth(self) -> bool:
        got = self.headers.get("X-Agent-Token", "")
        return bool(TOKEN) and hmac.compare_digest(got, TOKEN)

    def _send(self, code: int, body=None):
        data = b"" if body is None else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if data:
            self.wfile.write(data)

    def _handle(self, method: str):
        if not self._auth():
            return self._send(401, {"detail": "нет токена"})
        path = self.path.split("?", 1)[0].rstrip("/")
        try:
            if method == "GET" and path == "/queue":
                return self._send(200, parse_queue(run(CMD_QUEUE)))
            if method == "POST" and path == "/queue/flush":
                run(CMD_FLUSH)
                return self._send(204)
            if method == "DELETE" and path.startswith("/queue/"):
                qid = path[len("/queue/"):]
                if not QUEUE_ID_RE.match(qid):
                    return self._send(400, {"detail": "некорректный id"})
                run(CMD_DELETE + [qid])
                return self._send(204)
            if method == "GET" and path == "/quota":
                return self._send(200, parse_quota(run(CMD_QUOTA)))
            if method == "GET" and path == "/antivirus":
                return self._send(200, antivirus_info())
            if method == "POST" and path == "/antivirus/update":
                run(CMD_AV_UPDATE)
                return self._send(202)
            if method == "GET" and path == "/system":
                return self._send(200, system_info())
            if method == "GET" and path == "/settings":
                return self._send(200, json.loads(run(CMD_SETTINGS + ["get"])))
            if method == "POST" and path.startswith("/settings/"):
                _, _, rest = path.partition("/settings/")
                service, _, key = rest.partition("/")
                if service not in ("postfix", "dovecot") or not KEY_RE.match(key):
                    return self._send(400, {"detail": "некорректный путь"})
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    return self._send(400, {"detail": "некорректный Content-Length"})
                if not 0 <= length <= 4096:
                    return self._send(400, {"detail": "слишком большое тело запроса"})
                body = json.loads(self.rfile.read(length) or b"{}")
                value = str(body.get("value", ""))
                if len(value) > 250 or "\n" in value:
                    return self._send(400, {"detail": "некорректное значение"})
                return self._send(200, json.loads(run(CMD_SETTINGS + ["set", service, key, value])))
            return self._send(404, {"detail": "нет такого пути"})
        except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            return self._send(500, {"detail": str(e)})

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_DELETE(self):
        self._handle("DELETE")


def main() -> None:
    if not TOKEN or len(TOKEN) < 32:
        sys.exit("AGENT_TOKEN не задан или короче 32 символов (agent/.env)")
    srv = ThreadingHTTPServer((HOST or "127.0.0.1", int(PORT or 8025)), Handler)
    sys.stderr.write(f"mail-agent слушает {HOST}:{PORT}\n")
    srv.serve_forever()


if __name__ == "__main__":
    main()
