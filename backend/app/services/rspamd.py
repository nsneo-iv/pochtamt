"""Клиент контроллера Rspamd (127.0.0.1:11334): статистика, пороги, веса символов, списки, история, обучение.

Все изменения делает сам Rspamd через свой API (пишет в /var/lib/rspamd/rspamd_dynamic и файлы карт),
бэкенд на хост не ходит. Пароль — RSPAMD_PASSWORD (он же enable_password в local.d/worker-controller.inc).
"""
import httpx

from ..config import settings

# карты multimap (rspamd/local.d/multimap.conf): id в панели -> имя файла и подпись
LISTS = {
    "whitelist_from": ("whitelist_from.map", "Белый список отправителей", "адрес или домен; письма получают -10 баллов"),
    "blacklist_from": ("blacklist_from.map", "Чёрный список отправителей", "адрес или домен; письма отклоняются"),
    "whitelist_ip": ("whitelist_ip.map", "Белый список IP", "адрес или сеть CIDR; -10 баллов"),
    "blacklist_ip": ("blacklist_ip.map", "Чёрный список IP", "адрес или сеть CIDR; отклоняются"),
}
ACTIONS = {"greylist": "greylist", "add_header": "add header", "reject": "reject"}


class RspamdError(Exception):
    pass


def _client() -> httpx.Client:
    if not settings.rspamd_password:
        raise RspamdError("RSPAMD_PASSWORD не задан")
    return httpx.Client(base_url=settings.rspamd_url, timeout=15,
                        headers={"Password": settings.rspamd_password})


def _req(method: str, path: str, **kw):
    try:
        with _client() as c:
            r = c.request(method, path, **kw)
    except httpx.HTTPError as e:
        raise RspamdError(str(e))
    if r.status_code >= 400:
        raise RspamdError(f"{r.status_code}: {r.text[:200]}")
    if not r.content:
        return None
    try:
        return r.json()
    except ValueError:
        return r.text


def stat() -> dict | None:
    """Сводные счётчики или None, если Rspamd недоступен (для /stats — без исключений)."""
    try:
        d = _req("GET", "/stat")
    except RspamdError:
        return None
    actions = d.get("actions", {})
    return {
        "scanned": d.get("scanned", 0), "ham": d.get("ham_count", 0), "spam": d.get("spam_count", 0),
        "reject": actions.get("reject", 0), "add_header": actions.get("add header", 0),
        "greylist": actions.get("greylist", 0), "no_action": actions.get("no action", 0),
        "learned": d.get("learned", 0), "connections": d.get("connections", 0), "uptime": d.get("uptime", 0),
    }


# ---------------------------------------------------------------- пороги ----
def get_actions() -> dict:
    rows = _req("GET", "/actions")
    by = {r["action"]: r["value"] for r in rows}
    return {k: by.get(v) for k, v in ACTIONS.items()}


def set_actions(values: dict) -> dict:
    # формат контроллера (controller.c, saveactions): ровно 4 значения в порядке
    # [reject, rewrite subject, add header, greylist]; null — «не менять»
    payload = [float(values["reject"]), None, float(values["add_header"]), float(values["greylist"])]
    _req("POST", "/saveactions", json=payload)
    return get_actions()


# ---------------------------------------------------------------- символы ----
def get_symbols(q: str | None = None) -> list[dict]:
    out = []
    for g in _req("GET", "/symbols"):
        for r in g.get("rules", []):
            name = r.get("symbol", "")
            if q and q.lower() not in name.lower() and q.lower() not in (r.get("description") or "").lower():
                continue
            out.append({"name": name, "score": r.get("weight", 0.0), "description": r.get("description") or "",
                        "group": g.get("group", ""), "frequency": round(r.get("frequency", 0.0), 3)})
    return sorted(out, key=lambda x: (x["group"], x["name"]))


def set_symbols(items: list[dict]) -> None:
    _req("POST", "/savesymbols", json=[{"name": i["name"], "value": float(i["score"])} for i in items])


# ---------------------------------------------------------------- списки (карты multimap) ----
def _map_ids() -> dict[str, int]:
    """{id списка: id карты в Rspamd} по имени файла карты."""
    ids = {}
    for m in _req("GET", "/maps"):
        uri = m.get("uri", "")
        for key, (fname, _, _) in LISTS.items():
            if uri.endswith("/" + fname):
                ids[key] = m["map"]
    return ids


def get_list(key: str, map_id: int | None = None) -> dict:
    fname, title, descr = LISTS[key]
    mid = map_id or _map_ids().get(key)
    entries: list[str] = []
    if mid is not None:
        text = _req("GET", "/getmap", headers={"Map": str(mid)})
        if isinstance(text, str):
            entries = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    return {"id": key, "title": title, "description": descr, "entries": entries, "count": len(entries),
            "available": mid is not None}


def get_lists() -> list[dict]:
    ids = _map_ids()
    return [get_list(k, ids.get(k)) for k in LISTS]


def set_list(key: str, entries: list[str]) -> dict:
    mid = _map_ids().get(key)
    if mid is None:
        raise RspamdError(f"карта {LISTS[key][0]} не найдена в Rspamd (см. rspamd/local.d/multimap.conf)")
    body = "\n".join(entries) + ("\n" if entries else "")
    _req("POST", "/savemap", headers={"Map": str(mid), "Content-Type": "text/plain"}, content=body.encode())
    return get_list(key, mid)


# ---------------------------------------------------------------- история ----
def history(limit: int = 100, action: str | None = None, q: str | None = None) -> list[dict]:
    d = _req("GET", "/history")
    rows = d.get("rows", []) if isinstance(d, dict) else []
    out = []
    for r in rows:   # Rspamd отдаёт новые первыми
        act = r.get("action", "")
        if action and act != action:
            continue
        syms = r.get("symbols", {})
        if isinstance(syms, dict):
            symbols = sorted(({"name": k, "score": v.get("score", 0.0) if isinstance(v, dict) else 0.0}
                              for k, v in syms.items()), key=lambda s: -abs(s["score"]))
        else:
            symbols = [{"name": s, "score": 0.0} for s in syms]
        row = {
            "time": r.get("unix_time", 0), "ip": r.get("ip", ""), "user": r.get("user") or "",
            "sender": r.get("sender_smtp") or r.get("sender_mime") or "",
            "recipients": r.get("rcpt_smtp") or r.get("rcpt_mime") or [],
            "subject": r.get("subject") or "", "score": round(r.get("score", 0.0), 2),
            "required_score": r.get("required_score", 0), "action": act, "size": r.get("size", 0),
            "symbols": symbols, "scan_time": round(r.get("time_real", 0.0), 3),
            "message_id": r.get("message-id", ""),
        }
        if q:
            ql = q.lower()
            hay = " ".join([row["sender"], row["subject"], row["ip"], " ".join(row["recipients"])]).lower()
            if ql not in hay:
                continue
        out.append(row)
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------- обучение ----
def learn(kind: str, message: bytes) -> None:
    _req("POST", "/learnspam" if kind == "spam" else "/learnham", content=message,
         headers={"Content-Type": "message/rfc822"})
