"""Sieve-скрипт ящика (автоответ + пользовательские правила) через ManageSieve.

Бэкенд входит как master-пользователь Dovecot: логин «<ящик>*panel» с паролем SIEVE_MASTER_PASSWORD
(dovecot.conf: auth_master_user_separator, passdb passwd-file master = yes). Скрипт называется «panel»
и делается активным; пересылка в нём не живёт — она делается алиасом в базе (надёжнее, на уровне SMTP).
"""
import datetime as dt
import re

from sievelib.managesieve import Client

from ..config import settings

SCRIPT_NAME = "panel"
# расширения, доступные пользовательским правилам без собственного require (Pigeonhole их поддерживает)
CUSTOM_EXTENSIONS = ["fileinto", "imap4flags", "envelope", "relational", "comparator-i;ascii-numeric", "regex", "copy",
                     "body", "variables", "mailbox", "date", "subaddress", "duplicate"]
REQUIRE_RE = re.compile(r'^\s*require\s+(\[[^\]]*\]|"[^"]*")\s*;\s*$', re.M)


class SieveError(Exception):
    pass


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def build_script(st: dict) -> str:
    """Текст скрипта по строке mailbox_settings. Пустые настройки — пустой (но валидный) скрипт."""
    parts = ['# Скрипт сгенерирован панелью Pochtamt. Правки вручную будут перезаписаны.']
    req = set()
    if st.get("autoreply_enabled"):
        req |= {"vacation"}
        conds = []
        if st.get("autoreply_from"):
            req |= {"date", "relational"}
            conds.append(f'currentdate :value "ge" "date" "{st["autoreply_from"]:%Y-%m-%d}"')
        if st.get("autoreply_to"):
            req |= {"date", "relational"}
            conds.append(f'currentdate :value "le" "date" "{st["autoreply_to"]:%Y-%m-%d}"')
        subject = _esc(st.get("autoreply_subject") or "Автоответ")
        body = _esc(st.get("autoreply_body") or "")
        action = f'vacation :days 1 :subject "{subject}" "{body}";'
        if conds:
            parts.append(f"if allof({', '.join(conds)}) {{\n    {action}\n}}")
        else:
            parts.append(action)
    custom = (st.get("sieve_custom") or "").strip()
    if custom:
        # require допустим только в начале скрипта: вытаскиваем их из правил пользователя и сливаем в общий список
        for m in REQUIRE_RE.finditer(custom):
            req |= {x.strip().strip('"') for x in m.group(1).strip("[]").split(",") if x.strip()}
        custom = REQUIRE_RE.sub("", custom).strip()
        req |= set(CUSTOM_EXTENSIONS)
        parts.append("# --- пользовательские правила ---")
        parts.append(custom)
    head = ""
    if req:
        head = "require [" + ", ".join(f'"{r}"' for r in sorted(req)) + "];\n"
    return head + "\n".join(parts) + "\n"


def _client(address: str) -> Client:
    if not settings.sieve_master_password:
        raise SieveError("SIEVE_MASTER_PASSWORD не задан")
    c = Client(settings.sieve_host, settings.sieve_port, debug=False)
    user = f"{address}*{settings.sieve_master_user}"
    try:
        ok = c.connect(user, settings.sieve_master_password, starttls=True, authmech="PLAIN")
    except Exception as e:  # sievelib бросает разные классы
        raise SieveError(f"ManageSieve: {e}")
    if not ok:
        raise SieveError(f"ManageSieve: вход не удался ({c.errmsg.decode(errors='replace') if c.errmsg else 'нет ответа'})")
    return c


def check(address: str, script: str) -> str | None:
    """Проверка синтаксиса на сервере; None — ок, иначе текст ошибки."""
    c = _client(address)
    try:
        if c.checkscript(script):
            return None
        return (c.errmsg or b"error").decode(errors="replace")
    finally:
        c.logout()


def upload(address: str, script: str) -> None:
    c = _client(address)
    try:
        if not c.checkscript(script):
            raise SieveError("скрипт не прошёл проверку: " + (c.errmsg or b"").decode(errors="replace"))
        if not c.putscript(SCRIPT_NAME, script):
            raise SieveError("не удалось сохранить скрипт: " + (c.errmsg or b"").decode(errors="replace"))
        if not c.setactive(SCRIPT_NAME):
            raise SieveError("не удалось активировать скрипт: " + (c.errmsg or b"").decode(errors="replace"))
    finally:
        c.logout()


def current(address: str) -> dict:
    """Что сейчас на сервере: список скриптов, активный, текст скрипта панели."""
    c = _client(address)
    try:
        active, scripts = c.listscripts()
        text = c.getscript(SCRIPT_NAME) if SCRIPT_NAME in scripts else None
        return {"active": active, "scripts": scripts, "panel_script": text, "checked_at": dt.datetime.now(dt.timezone.utc)}
    finally:
        c.logout()
