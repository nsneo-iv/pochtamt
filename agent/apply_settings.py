#!/usr/bin/env python3
"""Помощник агента для глобальных параметров Postfix/Dovecot. Запускается через sudo (root), сам — граница доверия:
меняет только ключи из белого списка PARAMS и только значения, прошедшие проверку. Копия реестра —
backend/app/services/hostconf.py; при изменении править оба.

    apply_settings.py get                       -> JSON {key: value} по всем ключам реестра
    apply_settings.py set postfix KEY VALUE     -> postconf -e и postfix reload
    apply_settings.py set dovecot KEY VALUE     -> /etc/dovecot/panel.conf, doveconf -n, doveadm reload
"""
import json
import os
import re
import subprocess
import sys

PANEL_CONF = "/etc/dovecot/panel.conf"

PARAMS = {
    "message_size_limit": ("postfix", "int", 1_048_576, 209_715_200),
    "smtpd_client_connection_rate_limit": ("postfix", "int", 0, 10000),
    "smtpd_client_message_rate_limit": ("postfix", "int", 0, 100000),
    "smtpd_client_recipient_rate_limit": ("postfix", "int", 0, 100000),
    "anvil_rate_time_unit": ("postfix", "re", r"^\d{1,5}s$"),
    "smtpd_banner": ("postfix", "re", r"^\$myhostname( [A-Za-z0-9 ._-]{0,80})?$"),
    "smtpd_tls_protocols": ("postfix", "enum", [">=TLSv1.2", ">=TLSv1.3"]),
    "smtpd_tls_mandatory_protocols": ("postfix", "enum", [">=TLSv1.2", ">=TLSv1.3"]),
    "smtp_tls_security_level": ("postfix", "enum", ["may", "encrypt", "dane"]),
    "mynetworks": ("postfix", "re", r"^([0-9a-fA-F:.\[\]/]+)(,? +[0-9a-fA-F:.\[\]/]+)*$"),
    "maximal_queue_lifetime": ("postfix", "re", r"^\d{1,4}[smhdw]$"),
    "bounce_queue_lifetime": ("postfix", "re", r"^\d{1,4}[smhdw]$"),
    "disable_vrfy_command": ("postfix", "enum", ["yes", "no"]),
    "smtpd_helo_required": ("postfix", "enum", ["yes", "no"]),
    "mail_max_userip_connections": ("dovecot", "int", 1, 1000),
    "auth_failure_delay": ("dovecot", "re", r"^\d{1,3} secs$"),
    "imap_idle_notify_interval": ("dovecot", "re", r"^\d{1,3} mins$"),
    "quota_exceeded_message": ("dovecot", "re", r"^[\w .,!?:/()-]{1,200}$"),
    "lmtp_rcpt_check_quota": ("dovecot", "enum", ["yes", "no"]),
}


def die(msg: str, code: int = 2) -> None:
    print(msg, file=sys.stderr)
    sys.exit(code)


def _check_nets(v: str) -> None:
    """mynetworks: только loopback и частные сети не шире /16 (v4) и /64 (v6) — иначе панель могла бы
    одним запросом сделать сервер открытым релеем (0.0.0.0/0)."""
    import ipaddress
    for tok in re.split(r"[,\s]+", v.strip()):
        if not tok:
            continue
        try:
            net = ipaddress.ip_network(tok.replace("[", "").replace("]", ""), strict=False)
        except ValueError:
            die(f"mynetworks: {tok!r} - не адрес и не сеть")
        if not (net.is_loopback or net.is_private):
            die(f"mynetworks: {tok} - только частные сети и loopback")
        if net.prefixlen < (16 if net.version == 4 else 64) and not net.is_loopback:
            die(f"mynetworks: {tok} - сеть слишком широкая (не шире /16)")


def validate(key: str, value: str) -> str:
    p = PARAMS.get(key)
    if not p:
        die(f"параметр {key} не разрешён")
    v = value.strip()
    if p[1] == "int":
        if not re.fullmatch(r"\d{1,12}", v) or not (p[2] <= int(v) <= p[3]):
            die(f"{key}: недопустимое значение")
        return str(int(v))
    if p[1] == "enum":
        if v not in p[2]:
            die(f"{key}: недопустимое значение")
        return v
    if not re.fullmatch(p[2], v):
        die(f"{key}: недопустимое значение")
    if key == "mynetworks":
        _check_nets(v)
    return v


def run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        die((r.stderr or r.stdout).strip()[:500], 3)
    return r.stdout


def read_panel_conf() -> dict:
    out = {}
    if os.path.exists(PANEL_CONF):
        with open(PANEL_CONF, encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.lstrip().startswith("#"):
                    k, _, v = line.partition("=")
                    out[k.strip()] = v.strip()
    return out


def write_panel_conf(values: dict) -> None:
    lines = ["# Параметры, заданные из панели (agent/apply_settings.py). Не править вручную.\n"]
    for k in sorted(values):
        lines.append(f"{k} = {values[k]}\n")
    tmp = PANEL_CONF + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.writelines(lines)
    os.chmod(tmp, 0o644)
    os.replace(tmp, PANEL_CONF)


def cmd_get() -> None:
    out = {}
    for k, p in PARAMS.items():
        if p[0] == "postfix":
            out[k] = run(["/usr/sbin/postconf", "-h", k]).strip()
        else:
            # doveconf печатает «key = value» с учётом panel.conf
            line = run(["/usr/bin/doveconf", "-h", k]).strip()
            out[k] = line
    print(json.dumps(out, ensure_ascii=False))


def cmd_set(service: str, key: str, value: str) -> None:
    if service not in ("postfix", "dovecot") or PARAMS.get(key, ("",))[0] != service:
        die("служба не соответствует ключу")
    v = validate(key, value)
    if service == "postfix":
        run(["/usr/sbin/postconf", "-e", f"{key}={v}"])
        run(["/usr/sbin/postfix", "reload"])
    else:
        conf = read_panel_conf()
        old = conf.get(key)
        conf[key] = v
        write_panel_conf(conf)
        r = subprocess.run(["/usr/bin/doveconf", "-n"], capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            # откат: Dovecot не принял значение
            if old is None:
                conf.pop(key, None)
            else:
                conf[key] = old
            write_panel_conf(conf)
            die("Dovecot не принял значение: " + (r.stderr or r.stdout).strip()[:300], 3)
        run(["/usr/bin/doveadm", "reload"])
    print(json.dumps({key: v}, ensure_ascii=False))


def main() -> None:
    a = sys.argv[1:]
    if a == ["get"]:
        cmd_get()
    elif len(a) == 4 and a[0] == "set":
        cmd_set(a[1], a[2], a[3])
    else:
        die(__doc__)


if __name__ == "__main__":
    main()
