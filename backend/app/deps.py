"""Зависимости FastAPI: текущий админ, проверка роли и доступа к домену."""
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import db
from .models import UserOut
from .security import read_token

bearer = HTTPBearer(auto_error=False)


def load_admin(login: str) -> UserOut | None:
    row = db.fetch_one("SELECT login, display_name, role FROM admins WHERE login = %s AND active", (login,))
    if not row:
        return None
    domains = [r["domain"] for r in db.fetch_all("SELECT domain FROM admin_domains WHERE login = %s ORDER BY 1", (login,))]
    return UserOut(login=row["login"], display_name=row["display_name"], role=row["role"], domains=domains)


def current_admin(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> UserOut:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "требуется авторизация")
    login = read_token(creds.credentials, "admin")
    if not login:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "сессия недействительна")
    admin = load_admin(login)
    if not admin:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "учётная запись отключена")
    return admin


def superadmin(admin: UserOut = Depends(current_admin)) -> UserOut:
    if admin.role != "superadmin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "нужны права суперадминистратора")
    return admin


def check_domain(admin: UserOut, domain: str) -> None:
    """Доменный админ работает только со своими доменами."""
    if admin.role == "superadmin":
        return
    if domain not in admin.domains:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"нет доступа к домену {domain}")


def visible_domains(admin: UserOut) -> list[str] | None:
    """None — видны все домены (суперадмин), иначе список доступных."""
    return None if admin.role == "superadmin" else admin.domains


def client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None
