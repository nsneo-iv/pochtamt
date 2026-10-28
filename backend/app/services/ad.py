"""Active Directory (необязательный модуль): проверка пароля админа и синхронизация ящиков/рассылок.
Выключен, если AD_LDAP_URI пуст: authenticate() всегда отказывает, sync() поднимает ADError.

Синхронизация:
  * пользователи AD с атрибутом mail в одном из наших доменов -> ящики auth = ad;
    отключённые в AD или пропавшие -> ящик active = false (только для auth = ad);
  * рассылки с ad_group -> состав = mail всех участников группы (с вложенностью).
"""
import ssl
from typing import Any

import ldap3
from ldap3.core.exceptions import LDAPException

from .. import db
from ..audit import log
from ..config import settings
from ..models import SyncReport, norm_address
from ..routers.lists import set_members

UAC_DISABLED = 2
IN_CHAIN = "1.2.840.113556.1.4.1941"  # LDAP_MATCHING_RULE_IN_CHAIN — вложенные группы


class ADError(Exception):
    pass


def enabled() -> bool:
    return settings.ad_enabled


def normalize_login(login: str) -> str:
    """'user', 'CORP\\user', 'user@corp.local' -> 'user@corp.local' (нижний регистр).
    Без AD логин админа — произвольное имя (например, 'admin'), только приводится к нижнему регистру."""
    login = login.strip().lower()
    if not settings.ad_enabled:
        return login
    if "\\" in login:
        nb, _, user = login.partition("\\")
        if nb.upper() == settings.ad_netbios.upper():
            return f"{user}@{settings.ad_upn_suffix}"
        return f"{user}@{nb}"
    if "@" not in login and settings.ad_upn_suffix:
        return f"{login}@{settings.ad_upn_suffix}"
    return login


def _server() -> ldap3.Server:
    tls = ldap3.Tls(validate=ssl.CERT_REQUIRED if settings.ad_tls_verify else ssl.CERT_NONE)
    return ldap3.Server(settings.ad_ldap_uri, tls=tls, get_info=ldap3.NONE, connect_timeout=10)


def _service_conn() -> ldap3.Connection:
    if not settings.ad_enabled:
        raise ADError("Active Directory не настроен (AD_LDAP_URI пуст)")
    try:
        # referrals не преследуем: AD отдаёт их на дочерние домены, поиск идёт через Global Catalog (порт 3268)
        conn = ldap3.Connection(_server(), user=settings.ad_bind_user, password=settings.ad_bind_password,
                                auto_bind=True, receive_timeout=20, auto_referrals=False)
    except LDAPException as e:
        raise ADError(str(e))
    return conn


def authenticate(upn: str, password: str) -> dict[str, Any] | None:
    """Bind под учёткой пользователя. Возвращает {upn, display_name} или None."""
    if not password or not settings.ad_enabled:
        return None
    try:
        conn = ldap3.Connection(_server(), user=upn, password=password, auto_bind=True, receive_timeout=20,
                                auto_referrals=False)
    except LDAPException:
        return None
    try:
        conn.search(settings.ad_base_dn, f"(&(objectClass=user)(userPrincipalName={ldap3.utils.conv.escape_filter_chars(upn)}))",
                    attributes=["displayName", "userAccountControl"])
        if not conn.entries:
            return {"upn": upn, "display_name": ""}
        e = conn.entries[0]
        if int(e.userAccountControl.value or 0) & UAC_DISABLED:
            return None
        return {"upn": upn, "display_name": str(e.displayName.value or "")}
    except LDAPException:
        return {"upn": upn, "display_name": ""}
    finally:
        conn.unbind()


def _paged_search(conn: ldap3.Connection, flt: str, attrs: list[str]) -> list:
    """Все страницы результата. Один conn.search(paged_size=N) вернул бы только первые N записей,
    а остальных пользователей синхронизация сочла бы исчезнувшими и отключила бы их ящики."""
    entries: list = []
    cookie = None
    while True:
        conn.search(settings.ad_base_dn, flt, attributes=attrs, paged_size=500, paged_cookie=cookie)
        entries.extend(conn.entries)
        cookie = conn.result.get("controls", {}).get("1.2.840.113556.1.4.319", {}).get("value", {}).get("cookie")
        if not cookie:
            return entries


def _users_with_mail(conn: ldap3.Connection, domains: list[str]) -> dict[str, dict]:
    """{address: {upn, name, disabled}} по всем учёткам с mail в наших доменах."""
    out: dict[str, dict] = {}
    flt = "(&(objectClass=user)(objectCategory=person)(mail=*))"
    entries = _paged_search(conn, flt, ["mail", "userPrincipalName", "displayName", "userAccountControl"])
    for e in entries:
        try:
            addr = norm_address(str(e.mail.value))
        except ValueError:
            continue
        if addr.rpartition("@")[2] not in domains or not e.userPrincipalName.value:
            continue
        out[addr] = {"upn": str(e.userPrincipalName.value).lower(), "name": str(e.displayName.value or ""),
                     "disabled": bool(int(e.userAccountControl.value or 0) & UAC_DISABLED)}
    return out


def _group_members(conn: ldap3.Connection, group_dn: str) -> list[str]:
    """Адреса (mail) всех включённых пользователей группы, включая вложенные группы."""
    dn = ldap3.utils.conv.escape_filter_chars(group_dn)
    flt = f"(&(objectClass=user)(mail=*)(memberOf:{IN_CHAIN}:={dn})(!(userAccountControl:1.2.840.113556.1.4.803:=2)))"
    members = set()
    for e in _paged_search(conn, flt, ["mail"]):
        try:
            members.add(norm_address(str(e.mail.value)))
        except ValueError:
            pass
    return sorted(members)


def sync(apply: bool, actor: str = "system") -> SyncReport:
    report = SyncReport()
    domains = [r["name"] for r in db.fetch_all("SELECT name FROM domains WHERE active")]
    conn = _service_conn()
    try:
        ad_users = _users_with_mail(conn, domains)
        existing = {r["address"]: r for r in db.fetch_all(
            "SELECT address, domain, local_part, name, auth, ad_upn, active FROM mailboxes")}
        taken = {r["address"] for r in db.fetch_all("SELECT address FROM aliases UNION SELECT address FROM lists")}

        creates, updates, disables = [], [], []
        for addr, u in ad_users.items():
            cur = existing.get(addr)
            if cur is None:
                if u["disabled"]:
                    continue
                if addr in taken:
                    report.errors.append(f"{addr}: адрес занят алиасом или рассылкой")
                    continue
                creates.append((addr, u))
            elif cur["auth"] == "ad":
                if u["disabled"] and cur["active"]:
                    disables.append(addr)
                elif not u["disabled"] and (cur["name"] != u["name"] or cur["ad_upn"] != u["upn"] or not cur["active"]):
                    updates.append((addr, u))
        for addr, cur in existing.items():
            if cur["auth"] == "ad" and cur["active"] and addr not in ad_users:
                disables.append(addr)

        lists = db.fetch_all("SELECT address, ad_group FROM lists WHERE ad_group IS NOT NULL AND active")
        list_updates = []
        for lst in lists:
            try:
                members = _group_members(conn, lst["ad_group"])
            except LDAPException as e:
                report.errors.append(f"{lst['address']}: {e}")
                continue
            cur = sorted(r["member"] for r in db.fetch_all("SELECT member FROM list_members WHERE list = %s",
                                                           (lst["address"],)))
            if cur != members:
                list_updates.append((lst["address"], members))
    finally:
        conn.unbind()

    report.create = [a for a, _ in creates]
    report.update = [a for a, _ in updates]
    report.disable = sorted(set(disables))
    report.lists = [a for a, _ in list_updates]
    if not apply:
        return report

    with db.tx() as c:
        for addr, u in creates:
            local, domain = addr.rpartition("@")[0], addr.rpartition("@")[2]
            c.execute("INSERT INTO mailboxes (address, domain, local_part, name, auth, ad_upn, quota_mb, active) "
                      "SELECT %s, %s, %s, %s, 'ad', %s, COALESCE(NULLIF(d.max_quota_mb, 0), 1024), true "
                      "FROM domains d WHERE d.name = %s", (addr, domain, local, u["name"], u["upn"], domain))
            log(c, actor, "mailbox.create", addr, {"source": "ad", "ad_upn": u["upn"]})
        for addr, u in updates:
            c.execute("UPDATE mailboxes SET name = %s, ad_upn = %s, active = true WHERE address = %s",
                      (u["name"], u["upn"], addr))
            log(c, actor, "mailbox.update", addr, {"source": "ad", "name": u["name"], "ad_upn": u["upn"]})
        for addr in report.disable:
            c.execute("UPDATE mailboxes SET active = false WHERE address = %s", (addr,))
            log(c, actor, "mailbox.disable", addr, {"source": "ad"})
        for addr, members in list_updates:
            set_members(c, addr, members)
            c.execute("UPDATE lists SET synced_at = now() WHERE address = %s", (addr,))
            log(c, actor, "list.sync", addr, {"members": members})
    return report
