"""Личный кабинет пользователя: вход своим ящиком, пароль, автоответ, пересылка, правила Sieve."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .. import db
from ..audit import log
from ..deps import client_ip
from ..models import (Autoreply, Forward, MailboxSettingsOut, MeLoginIn, MeLoginOut, MeOut, MePasswordIn, MeSettingsIn)
from ..security import DUMMY_HASH, hash_password, issue_token, needs_rehash, read_token, verify_password
from ..services import ad, mailbox_settings, throttle

router = APIRouter(prefix="/me", tags=["me"])
bearer = HTTPBearer(auto_error=False)


def _mailbox(address: str) -> dict | None:
    return db.fetch_one(
        "SELECT m.address, m.domain, m.name, m.auth, m.ad_upn, m.password, m.quota_mb, m.active, m.mode,"
        " COALESCE(u.bytes, 0) / 1048576 AS used_mb, COALESCE(u.messages, 0) AS messages"
        " FROM mailboxes m LEFT JOIN mailbox_usage u ON u.address = m.address WHERE m.address = %s", (address,))


def _me_out(m: dict) -> MeOut:
    return MeOut(address=m["address"], name=m["name"], domain=m["domain"], auth=m["auth"], quota_mb=m["quota_mb"],
                 used_mb=int(m["used_mb"]), messages=m["messages"], mode=m["mode"])


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "требуется вход")
    address = read_token(creds.credentials, "user")
    m = _mailbox(address) if address else None
    if not m or not m["active"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "сессия недействительна")
    return m


@router.post("/login", response_model=MeLoginOut)
def login(body: MeLoginIn, request: Request) -> MeLoginOut:
    ip = client_ip(request)
    address = body.address.strip().lower()
    throttle.check("me", address, ip)
    m = _mailbox(body.address)
    ok = False
    if m and m["active"]:
        if m["auth"] == "local" and m["password"]:
            ok = verify_password(body.password, m["password"])
            if ok and needs_rehash(m["password"]):
                # импортированный хеш (SSHA512) заменяем на bcrypt: пароль известен только в момент входа
                with db.tx() as conn:
                    conn.execute("UPDATE mailboxes SET password = %s WHERE address = %s",
                                 (hash_password(body.password), m["address"]))
        elif m["auth"] == "ad" and m["ad_upn"]:
            ok = ad.authenticate(m["ad_upn"], body.password) is not None
    else:
        # ящика нет/отключён: тратим то же время, что и на проверку пароля (иначе адреса перебираются по скорости ответа)
        verify_password(body.password, DUMMY_HASH)
    with db.tx() as conn:
        log(conn, body.address, "me.login" if ok else "me.auth.fail", body.address, {}, ip)
    if ok:
        throttle.reset("me", address, ip)
    else:
        throttle.fail("me", address, ip)
    if not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "неверный адрес или пароль")
    return MeLoginOut(token=issue_token(body.address, "user"), me=_me_out(m))


@router.get("", response_model=MeOut)
def me(m: dict = Depends(current_user)) -> MeOut:
    return _me_out(m)


@router.post("/password", status_code=204)
def change_password(body: MePasswordIn, request: Request, m: dict = Depends(current_user)) -> None:
    if m["auth"] != "local":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "пароль этого ящика меняется в Active Directory")
    ip = client_ip(request)
    throttle.check("me", m["address"], ip)
    if not m["password"] or not verify_password(body.current_password, m["password"]):
        throttle.fail("me", m["address"], ip)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "текущий пароль указан неверно")
    with db.tx() as conn:
        conn.execute("UPDATE mailboxes SET password = %s WHERE address = %s", (hash_password(body.password), m["address"]))
        log(conn, m["address"], "me.password", m["address"], {}, client_ip(request))


@router.get("/settings", response_model=MailboxSettingsOut)
def get_settings(m: dict = Depends(current_user)) -> dict:
    return mailbox_settings.get(m["address"])


@router.put("/settings", response_model=MailboxSettingsOut)
def put_settings(body: MeSettingsIn, request: Request, m: dict = Depends(current_user)) -> dict:
    address = m["address"]
    changed = body.model_dump(exclude_none=True)
    if body.sieve_custom is not None:
        err = mailbox_settings.check_custom(address, body.sieve_custom)
        if err:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"ошибка в правилах Sieve: {err}")
    try:
        with db.tx() as conn:
            if body.autoreply is not None:
                mailbox_settings.save_autoreply(conn, address, Autoreply(**body.autoreply.model_dump()))
            if body.forward is not None:
                mailbox_settings.save_forward(conn, address, Forward(**body.forward.model_dump()))
            if body.sieve_custom is not None:
                mailbox_settings.save_sieve_custom(conn, address, body.sieve_custom)
            log(conn, address, "me.settings", address, {k: (v if k != "autoreply" else "…") for k, v in changed.items()},
                client_ip(request))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    err = mailbox_settings.sync_sieve(address) if (body.autoreply is not None or body.sieve_custom is not None) else None
    out = mailbox_settings.get(address)
    out["sieve_error"] = err
    return out
