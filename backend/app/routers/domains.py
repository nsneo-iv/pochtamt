"""Домены и их DKIM-ключи."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from .. import db
from ..audit import log
from ..deps import check_domain, client_ip, current_admin, superadmin, visible_domains
from ..models import (DkimIn, DkimOut, DomainDashboard, DomainIn, DomainOut, DomainPatch, DomainSettings, DomainStats,
                      UserOut)
from ..services import dkim, dnscheck

router = APIRouter(prefix="/domains", tags=["domains"])

COLS = "name, description, max_mailboxes, max_quota_mb, active, created_at"


def _get(name: str) -> dict:
    row = db.fetch_one(f"SELECT {COLS} FROM domains WHERE name = %s", (name,))
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"домен {name} не найден")
    return row


@router.get("", response_model=list[DomainOut])
def list_domains(admin: UserOut = Depends(current_admin)) -> list[dict]:
    vis = visible_domains(admin)
    if vis is None:
        return db.fetch_all(f"SELECT {COLS} FROM domains ORDER BY name")
    return db.fetch_all(f"SELECT {COLS} FROM domains WHERE name = ANY(%s) ORDER BY name", (vis,))


@router.post("", response_model=DomainOut, status_code=201)
def create_domain(body: DomainIn, request: Request, admin: UserOut = Depends(superadmin)) -> dict:
    if db.fetch_one("SELECT 1 FROM domains WHERE name = %s", (body.name,)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"домен {body.name} уже есть")
    if db.fetch_one("SELECT 1 FROM domain_aliases WHERE alias_domain = %s", (body.name,)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{body.name} уже используется как доменный алиас")
    with db.tx() as conn:
        row = conn.execute(
            f"INSERT INTO domains (name, description, max_mailboxes, max_quota_mb, active) "
            f"VALUES (%s, %s, %s, %s, %s) RETURNING {COLS}",
            (body.name, body.description, body.max_mailboxes, body.max_quota_mb, body.active)).fetchone()
        log(conn, admin.login, "domain.create", body.name, body.model_dump(), client_ip(request))
    return row


@router.get("/{name}", response_model=DomainOut)
def get_domain(name: str, admin: UserOut = Depends(current_admin)) -> dict:
    name = name.lower()
    check_domain(admin, name)
    row = _get(name)
    s = db.fetch_one("SELECT mailboxes, aliases, lists, used_bytes FROM v_domain_stats WHERE domain = %s", (name,))
    row["stats"] = DomainStats(mailboxes=s["mailboxes"], aliases=s["aliases"], lists=s["lists"],
                               used_mb=int(s["used_bytes"] // (1024 * 1024)))
    return row


@router.put("/{name}", response_model=DomainOut)
def update_domain(name: str, body: DomainPatch, request: Request, admin: UserOut = Depends(superadmin)) -> dict:
    name = name.lower()
    _get(name)
    patch = body.model_dump(exclude_none=True)
    if not patch:
        return _get(name)
    sets = ", ".join(f"{k} = %s" for k in patch)
    with db.tx() as conn:
        row = conn.execute(f"UPDATE domains SET {sets} WHERE name = %s RETURNING {COLS}",
                           (*patch.values(), name)).fetchone()
        log(conn, admin.login, "domain.update", name, patch, client_ip(request))
    return row


@router.delete("/{name}", status_code=204)
def delete_domain(name: str, request: Request, admin: UserOut = Depends(superadmin)) -> Response:
    name = name.lower()
    _get(name)
    n = db.fetch_one("SELECT count(*) AS n FROM mailboxes WHERE domain = %s", (name,))["n"]
    if n:
        raise HTTPException(status.HTTP_409_CONFLICT, f"в домене {name} ещё {n} ящиков — сначала удалите их")
    with db.tx() as conn:
        dkim.remove(conn, name)
        conn.execute("DELETE FROM domains WHERE name = %s", (name,))
        log(conn, admin.login, "domain.delete", name, {}, client_ip(request))
    return Response(status_code=204)


# ---------------------------------------------------------------- DKIM ----
@router.get("/{name}/dkim", response_model=DkimOut | None)
def get_dkim(name: str, admin: UserOut = Depends(current_admin)) -> dict | None:
    name = name.lower()
    check_domain(admin, name)
    _get(name)
    return dkim.get(name)


@router.post("/{name}/dkim", response_model=DkimOut, status_code=201)
def create_dkim(name: str, body: DkimIn, request: Request, admin: UserOut = Depends(superadmin)) -> dict:
    name = name.lower()
    _get(name)
    with db.tx() as conn:
        out = dkim.create(conn, name, body.selector)
        log(conn, admin.login, "dkim.create", name, {"selector": body.selector}, client_ip(request))
    return out


@router.delete("/{name}/dkim", status_code=204)
def delete_dkim(name: str, request: Request, admin: UserOut = Depends(superadmin)) -> Response:
    name = name.lower()
    _get(name)
    with db.tx() as conn:
        dkim.remove(conn, name)
        log(conn, admin.login, "dkim.delete", name, {}, client_ip(request))
    return Response(status_code=204)


# ---------------------------------------------------------------- дашборд ----
@router.get("/{name}/dashboard", response_model=DomainDashboard)
def dashboard(name: str, admin: UserOut = Depends(current_admin)) -> dict:
    name = name.lower()
    check_domain(admin, name)
    domain = _get(name)
    st = db.fetch_one(
        "SELECT count(*) AS mailboxes, count(*) FILTER (WHERE active) AS mailboxes_active,"
        " count(*) FILTER (WHERE auth = 'ad') AS mailboxes_ad,"
        " COALESCE(sum(quota_mb), 0) AS quota_mb, count(*) FILTER (WHERE quota_mb = 0) AS unlimited"
        " FROM mailboxes WHERE domain = %s", (name,))
    cnt = db.fetch_one(
        "SELECT (SELECT count(*) FROM aliases WHERE domain = %s) AS aliases,"
        " (SELECT count(*) FROM lists WHERE domain = %s) AS lists,"
        " (SELECT COALESCE(sum(u.bytes), 0) FROM mailbox_usage u JOIN mailboxes m ON m.address = u.address"
        "  WHERE m.domain = %s) AS used_bytes", (name, name, name))
    stats = {"mailboxes": st["mailboxes"], "mailboxes_active": st["mailboxes_active"],
             "mailboxes_ad": st["mailboxes_ad"], "aliases": cnt["aliases"], "lists": cnt["lists"],
             "used_mb": int(cnt["used_bytes"] // 1048576), "quota_mb": int(st["quota_mb"]), "unlimited": st["unlimited"]}
    top = db.fetch_all(
        "SELECT m.address, m.name, m.quota_mb, m.active, COALESCE(u.bytes, 0) / 1048576 AS used_mb,"
        " CASE WHEN m.quota_mb > 0 THEN LEAST(100, COALESCE(u.bytes, 0) * 100 / (m.quota_mb::bigint * 1048576))"
        " ELSE 0 END AS percent"
        " FROM mailboxes m LEFT JOIN mailbox_usage u ON u.address = m.address"
        " WHERE m.domain = %s ORDER BY COALESCE(u.bytes, 0) DESC, m.address LIMIT 10", (name,))
    audit = db.fetch_all(
        "SELECT ts, actor, action, object, details FROM audit_log"
        " WHERE object = %s OR split_part(object, '@', 2) = %s ORDER BY ts DESC, id DESC LIMIT 10", (name, name))
    key = db.fetch_one("SELECT selector, public_key FROM dkim_keys WHERE domain = %s", (name,))
    dns = {
        "mx": dnscheck.check_mx(name),
        "spf": dnscheck.check_spf(name),
        "dkim": dnscheck.check_dkim(name, key["selector"] if key else None, key["public_key"] if key else None),
        "dmarc": dnscheck.check_dmarc(name),
    }
    return {"domain": domain, "stats": stats, "dkim": dkim.get(name), "dns": dns, "top_mailboxes": top,
            "recent_audit": audit}


# ---------------------------------------------------------------- настройки домена ----
@router.get("/{name}/settings", response_model=DomainSettings)
def get_settings(name: str, admin: UserOut = Depends(current_admin)) -> DomainSettings:
    name = name.lower()
    check_domain(admin, name)
    _get(name)
    row = db.fetch_one("SELECT transport, bcc_address, outbound_allowed FROM domain_settings WHERE domain = %s", (name,))
    return DomainSettings(**row) if row else DomainSettings()


@router.put("/{name}/settings", response_model=DomainSettings)
def put_settings(name: str, body: DomainSettings, request: Request, admin: UserOut = Depends(superadmin)) -> DomainSettings:
    name = name.lower()
    _get(name)
    with db.tx() as conn:
        conn.execute(
            "INSERT INTO domain_settings (domain, transport, bcc_address, outbound_allowed) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (domain) DO UPDATE SET transport = EXCLUDED.transport, bcc_address = EXCLUDED.bcc_address, "
            "outbound_allowed = EXCLUDED.outbound_allowed",
            (name, body.transport, body.bcc_address, body.outbound_allowed))
        log(conn, admin.login, "domain.settings", name, body.model_dump(), client_ip(request))
    return body
