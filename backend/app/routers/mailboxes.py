"""Почтовые ящики."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from .. import db
from ..audit import log
from ..deps import check_domain, client_ip, current_admin, visible_domains
from ..models import (MailboxIn, MailboxOut, MailboxPatch, MailboxSettingsIn, MailboxSettingsOut, PasswordIn, UserOut,
                      split_address)
from ..services import mailbox_settings
from ..security import hash_password

router = APIRouter(prefix="/mailboxes", tags=["mailboxes"])

SELECT = """
SELECT m.address, m.domain, m.name, m.auth, m.ad_upn, m.quota_mb, m.active, m.created_at,
       COALESCE(u.bytes, 0) / 1048576 AS used_mb
  FROM mailboxes m LEFT JOIN mailbox_usage u ON u.address = m.address
"""


def _get(address: str) -> dict:
    row = db.fetch_one(SELECT + " WHERE m.address = %s", (address,))
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"ящик {address} не найден")
    return row


def _check_limits(domain: str, quota_mb: int, adding: bool) -> None:
    d = db.fetch_one("SELECT max_mailboxes, max_quota_mb, active FROM domains WHERE name = %s", (domain,))
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"домен {domain} не найден")
    if d["max_quota_mb"] and (quota_mb == 0 or quota_mb > d["max_quota_mb"]):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"квота ящика не может превышать {d['max_quota_mb']} МБ для домена {domain}")
    if adding and d["max_mailboxes"]:
        n = db.fetch_one("SELECT count(*) AS n FROM mailboxes WHERE domain = %s", (domain,))["n"]
        if n >= d["max_mailboxes"]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"достигнут лимит ящиков домена {domain}: {d['max_mailboxes']}")


@router.get("", response_model=list[MailboxOut])
def list_mailboxes(domain: str | None = None, q: str | None = None,
                   admin: UserOut = Depends(current_admin)) -> list[dict]:
    where, params = [], []
    vis = visible_domains(admin)
    if domain:
        check_domain(admin, domain.lower())
        where.append("m.domain = %s")
        params.append(domain.lower())
    elif vis is not None:
        where.append("m.domain = ANY(%s)")
        params.append(vis)
    if q:
        where.append("(m.address ILIKE %s OR m.name ILIKE %s)")
        params += [f"%{q}%", f"%{q}%"]
    sql = SELECT + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY m.domain, m.address"
    return db.fetch_all(sql, params)


@router.post("", response_model=MailboxOut, status_code=201)
def create_mailbox(body: MailboxIn, request: Request, admin: UserOut = Depends(current_admin)) -> dict:
    local, domain = split_address(body.address)
    check_domain(admin, domain)
    if body.auth == "local" and not body.password:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "для auth=local нужен пароль")
    if body.auth == "ad" and not body.ad_upn:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "для auth=ad нужен ad_upn")
    if db.fetch_one("SELECT 1 FROM mailboxes WHERE address = %s", (body.address,)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"ящик {body.address} уже есть")
    if db.fetch_one("SELECT 1 FROM aliases WHERE address = %s UNION SELECT 1 FROM lists WHERE address = %s",
                    (body.address, body.address)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"адрес {body.address} занят алиасом или рассылкой")
    _check_limits(domain, body.quota_mb, adding=True)
    pw_hash = hash_password(body.password) if body.auth == "local" else None
    with db.tx() as conn:
        conn.execute(
            "INSERT INTO mailboxes (address, domain, local_part, name, auth, ad_upn, password, quota_mb, active) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (body.address, domain, local, body.name, body.auth, body.ad_upn if body.auth == "ad" else None,
             pw_hash, body.quota_mb, body.active))
        log(conn, admin.login, "mailbox.create", body.address,
            body.model_dump(exclude={"password"}), client_ip(request))
    return _get(body.address)


@router.get("/{address}", response_model=MailboxOut)
def get_mailbox(address: str, admin: UserOut = Depends(current_admin)) -> dict:
    row = _get(address.lower())
    check_domain(admin, row["domain"])
    return row


@router.put("/{address}", response_model=MailboxOut)
def update_mailbox(address: str, body: MailboxPatch, request: Request,
                   admin: UserOut = Depends(current_admin)) -> dict:
    address = address.lower()
    cur = _get(address)
    check_domain(admin, cur["domain"])
    patch = body.model_dump(exclude_none=True)
    if "quota_mb" in patch:
        _check_limits(cur["domain"], patch["quota_mb"], adding=False)
    auth = patch.get("auth", cur["auth"])
    if auth == "ad":
        patch["ad_upn"] = (patch.get("ad_upn") or cur["ad_upn"] or "").lower() or None
        if not patch["ad_upn"]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "для auth=ad нужен ad_upn")
        patch["password"] = None
    else:
        patch["ad_upn"] = None
        if cur["auth"] == "ad":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "переключение на auth=local: сначала задайте пароль через /password")
    if not patch:
        return cur
    sets = ", ".join(f"{k} = %s" for k in patch)
    with db.tx() as conn:
        conn.execute(f"UPDATE mailboxes SET {sets} WHERE address = %s", (*patch.values(), address))
        log(conn, admin.login, "mailbox.update", address, {k: v for k, v in patch.items() if k != "password"},
            client_ip(request))
    return _get(address)


@router.post("/{address}/password", status_code=204)
def set_password(address: str, body: PasswordIn, request: Request,
                 admin: UserOut = Depends(current_admin)) -> Response:
    address = address.lower()
    cur = _get(address)
    check_domain(admin, cur["domain"])
    with db.tx() as conn:
        # смена пароля переводит ящик на локальную аутентификацию
        conn.execute("UPDATE mailboxes SET password = %s, auth = 'local', ad_upn = NULL WHERE address = %s",
                     (hash_password(body.password), address))
        log(conn, admin.login, "mailbox.password", address, {}, client_ip(request))
    return Response(status_code=204)


@router.delete("/{address}", status_code=204)
def delete_mailbox(address: str, request: Request, admin: UserOut = Depends(current_admin)) -> Response:
    address = address.lower()
    cur = _get(address)
    check_domain(admin, cur["domain"])
    with db.tx() as conn:
        conn.execute("DELETE FROM mailboxes WHERE address = %s", (address,))
        log(conn, admin.login, "mailbox.delete", address, {}, client_ip(request))
    # Maildir на диске не трогаем: его чистит оператор вручную после проверки (см. README)
    return Response(status_code=204)


# ---------------------------------------------------------------- настройки ящика ----
@router.get("/{address}/settings", response_model=MailboxSettingsOut)
def get_settings(address: str, admin: UserOut = Depends(current_admin)) -> dict:
    address = address.lower()
    cur = _get(address)
    check_domain(admin, cur["domain"])
    return mailbox_settings.get(address)


@router.put("/{address}/settings", response_model=MailboxSettingsOut)
def put_settings(address: str, body: MailboxSettingsIn, request: Request,
                 admin: UserOut = Depends(current_admin)) -> dict:
    address = address.lower()
    cur = _get(address)
    check_domain(admin, cur["domain"])
    if body.sieve_custom is not None:
        err = mailbox_settings.check_custom(address, body.sieve_custom)
        if err:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"ошибка в правилах Sieve: {err}")
    try:
        with db.tx() as conn:
            if body.mode is not None:
                conn.execute("UPDATE mailboxes SET mode = %s WHERE address = %s", (body.mode, address))
            if body.autoreply is not None:
                mailbox_settings.save_autoreply(conn, address, body.autoreply)
            if body.forward is not None:
                mailbox_settings.save_forward(conn, address, body.forward)
            if body.sieve_custom is not None:
                mailbox_settings.save_sieve_custom(conn, address, body.sieve_custom)
            if "bcc_address" in body.model_fields_set:
                mailbox_settings.save_bcc(conn, address, body.bcc_address)
            log(conn, admin.login, "mailbox.settings", address,
                {k: v for k, v in body.model_dump(exclude_none=True).items() if k != "autoreply"} |
                ({"autoreply": body.autoreply.enabled} if body.autoreply else {}), client_ip(request))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    err = None
    if body.autoreply is not None or body.sieve_custom is not None:
        err = mailbox_settings.sync_sieve(address)
    out = mailbox_settings.get(address)
    out["sieve_error"] = err
    return out
