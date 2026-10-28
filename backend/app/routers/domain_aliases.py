"""Доменные алиасы (только суперадмин)."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from .. import db
from ..audit import log
from ..deps import client_ip, superadmin
from ..models import DomainAliasIn, DomainAliasOut, UserOut

router = APIRouter(prefix="/domain-aliases", tags=["domain-aliases"])


@router.get("", response_model=list[DomainAliasOut])
def list_domain_aliases(_: UserOut = Depends(superadmin)) -> list[dict]:
    return db.fetch_all("SELECT alias_domain, target_domain, active FROM domain_aliases ORDER BY alias_domain")


@router.post("", response_model=DomainAliasOut, status_code=201)
def create_domain_alias(body: DomainAliasIn, request: Request, admin: UserOut = Depends(superadmin)) -> dict:
    if not db.fetch_one("SELECT 1 FROM domains WHERE name = %s", (body.target_domain,)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"домен {body.target_domain} не найден")
    if db.fetch_one("SELECT 1 FROM domains WHERE name = %s", (body.alias_domain,)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{body.alias_domain} — это самостоятельный домен")
    if db.fetch_one("SELECT 1 FROM domain_aliases WHERE alias_domain = %s", (body.alias_domain,)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"доменный алиас {body.alias_domain} уже есть")
    with db.tx() as conn:
        row = conn.execute(
            "INSERT INTO domain_aliases (alias_domain, target_domain) VALUES (%s, %s) "
            "RETURNING alias_domain, target_domain, active", (body.alias_domain, body.target_domain)).fetchone()
        log(conn, admin.login, "domain_alias.create", body.alias_domain, body.model_dump(), client_ip(request))
    return row


@router.delete("/{alias_domain}", status_code=204)
def delete_domain_alias(alias_domain: str, request: Request, admin: UserOut = Depends(superadmin)) -> Response:
    alias_domain = alias_domain.lower()
    if not db.fetch_one("SELECT 1 FROM domain_aliases WHERE alias_domain = %s", (alias_domain,)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"доменный алиас {alias_domain} не найден")
    with db.tx() as conn:
        conn.execute("DELETE FROM domain_aliases WHERE alias_domain = %s", (alias_domain,))
        log(conn, admin.login, "domain_alias.delete", alias_domain, {}, client_ip(request))
    return Response(status_code=204)
