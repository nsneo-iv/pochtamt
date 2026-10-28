"""Алиасы, пересылки и catch-all."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from .. import db
from ..audit import log
from ..deps import check_domain, client_ip, current_admin, visible_domains
from ..models import AliasIn, AliasOut, AliasPatch, UserOut, split_address

router = APIRouter(prefix="/aliases", tags=["aliases"])

SELECT = """
SELECT a.address, a.domain, a.description, a.active, a.created_at,
       COALESCE((SELECT array_agg(t.target::text ORDER BY t.target) FROM alias_targets t WHERE t.alias = a.address),
                ARRAY[]::text[]) AS targets
  FROM aliases a
"""


def _get(address: str) -> dict:
    row = db.fetch_one(SELECT + " WHERE a.address = %s", (address,))
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"алиас {address} не найден")
    return row


def _set_targets(conn, address: str, targets: list[str]) -> None:
    conn.execute("DELETE FROM alias_targets WHERE alias = %s", (address,))
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO alias_targets (alias, target) VALUES (%s, %s)", [(address, t) for t in targets])


@router.get("", response_model=list[AliasOut])
def list_aliases(domain: str | None = None, q: str | None = None, admin: UserOut = Depends(current_admin)) -> list[dict]:
    where, params = [], []
    vis = visible_domains(admin)
    if domain:
        check_domain(admin, domain.lower())
        where.append("a.domain = %s")
        params.append(domain.lower())
    elif vis is not None:
        where.append("a.domain = ANY(%s)")
        params.append(vis)
    if q:
        where.append("(a.address ILIKE %s OR a.description ILIKE %s)")
        params += [f"%{q}%", f"%{q}%"]
    sql = SELECT + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY a.domain, a.address"
    return db.fetch_all(sql, params)


@router.post("", response_model=AliasOut, status_code=201)
def create_alias(body: AliasIn, request: Request, admin: UserOut = Depends(current_admin)) -> dict:
    _, domain = split_address(body.address)
    check_domain(admin, domain)
    if not db.fetch_one("SELECT 1 FROM domains WHERE name = %s", (domain,)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"домен {domain} не найден")
    if db.fetch_one("SELECT 1 FROM aliases WHERE address = %s", (body.address,)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"алиас {body.address} уже есть")
    if db.fetch_one("SELECT 1 FROM lists WHERE address = %s", (body.address,)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"адрес {body.address} занят рассылкой")
    if body.address in body.targets and len(body.targets) == 1:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "алиас не может указывать только сам на себя")
    with db.tx() as conn:
        conn.execute("INSERT INTO aliases (address, domain, description, active) VALUES (%s, %s, %s, %s)",
                     (body.address, domain, body.description, body.active))
        _set_targets(conn, body.address, body.targets)
        log(conn, admin.login, "alias.create", body.address, body.model_dump(), client_ip(request))
    return _get(body.address)


@router.get("/{address}", response_model=AliasOut)
def get_alias(address: str, admin: UserOut = Depends(current_admin)) -> dict:
    row = _get(address.lower())
    check_domain(admin, row["domain"])
    return row


@router.put("/{address}", response_model=AliasOut)
def update_alias(address: str, body: AliasPatch, request: Request, admin: UserOut = Depends(current_admin)) -> dict:
    address = address.lower()
    cur = _get(address)
    check_domain(admin, cur["domain"])
    patch = body.model_dump(exclude_none=True)
    targets = patch.pop("targets", None)
    with db.tx() as conn:
        if patch:
            sets = ", ".join(f"{k} = %s" for k in patch)
            conn.execute(f"UPDATE aliases SET {sets} WHERE address = %s", (*patch.values(), address))
        if targets is not None:
            _set_targets(conn, address, targets)
            patch["targets"] = targets
        log(conn, admin.login, "alias.update", address, patch, client_ip(request))
    return _get(address)


@router.delete("/{address}", status_code=204)
def delete_alias(address: str, request: Request, admin: UserOut = Depends(current_admin)) -> Response:
    address = address.lower()
    cur = _get(address)
    check_domain(admin, cur["domain"])
    with db.tx() as conn:
        conn.execute("DELETE FROM aliases WHERE address = %s", (address,))
        log(conn, admin.login, "alias.delete", address, {}, client_ip(request))
    return Response(status_code=204)
