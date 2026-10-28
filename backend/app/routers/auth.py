"""Вход админа: пароль проверяет локальный хеш (admins.password_hash) или Active Directory; роль — таблица admins."""
from fastapi import APIRouter, Depends, HTTPException, Request, status

from .. import db
from ..audit import log
from ..config import settings
from ..deps import client_ip, current_admin, load_admin
from ..models import AuthConfigOut, LoginIn, LoginOut, UserOut
from ..security import DUMMY_HASH, issue_token, verify_password
from ..services import ad, throttle

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/config", response_model=AuthConfigOut)
def config() -> AuthConfigOut:
    """Что умеет этот сервер (без авторизации): фронт прячет разделы AD, если AD не настроен."""
    hint = f"user@{settings.ad_upn_suffix}" if settings.ad_enabled and settings.ad_upn_suffix else "admin"
    return AuthConfigOut(ad_enabled=settings.ad_enabled, login_hint=hint)


def _check_password(upn: str, admin: UserOut | None, password: str) -> dict | None:
    """Локальный пароль — если у админа задан хеш; иначе bind в AD (если настроен). Неизвестный логин
    проходит фиктивную проверку bcrypt, чтобы по времени ответа нельзя было перебирать админов."""
    row = db.fetch_one("SELECT password_hash FROM admins WHERE login = %s AND active", (upn,))
    stored = row["password_hash"] if row else None
    if admin and stored:
        return {"upn": upn, "display_name": admin.display_name} if verify_password(password, stored) else None
    if ad.enabled():
        return ad.authenticate(upn, password)
    verify_password(password, DUMMY_HASH)
    return None


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, request: Request) -> LoginOut:
    upn = ad.normalize_login(body.login)
    ip = client_ip(request)
    throttle.check("admin", upn, ip)
    admin = load_admin(upn)
    # не раскрываем, есть ли такой админ: пароль проверяется всегда
    account = _check_password(upn, admin, body.password)
    if not account or not admin:
        throttle.fail("admin", upn, ip)
        with db.tx() as conn:
            log(conn, upn, "auth.fail", upn, {}, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "неверный логин или пароль, либо нет прав на панель")
    with db.tx() as conn:
        if account.get("display_name") and account["display_name"] != admin.display_name:
            conn.execute("UPDATE admins SET display_name = %s WHERE login = %s", (account["display_name"], upn))
            admin.display_name = account["display_name"]
        log(conn, upn, "auth.login", upn, {}, ip)
    throttle.reset("admin", upn, ip)
    return LoginOut(token=issue_token(upn), user=admin)


@router.get("/me", response_model=UserOut)
def me(admin: UserOut = Depends(current_admin)) -> UserOut:
    return admin
