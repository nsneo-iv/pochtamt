"""Рассылки (группы адресов), в том числе привязанные к группам AD."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from .. import db
from ..audit import log
from ..deps import check_domain, client_ip, current_admin, visible_domains
from ..models import ListIn, ListOut, ListPatch, UserOut, split_address

router = APIRouter(prefix="/lists", tags=["lists"])

SELECT = """
SELECT l.address, l.domain, l.name, l.ad_group, l.active, l.synced_at,
       COALESCE((SELECT array_agg(m.member::text ORDER BY m.member) FROM list_members m WHERE m.list = l.address),
                ARRAY[]::text[]) AS members
  FROM lists l
"""


def _get(address: str) -> dict:
    row = db.fetch_one(SELECT + " WHERE l.address = %s", (address,))
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"рассылка {address} не найдена")
    return row


def set_members(conn, address: str, members: list[str]) -> None:
    conn.execute("DELETE FROM list_members WHERE list = %s", (address,))
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO list_members (list, member) VALUES (%s, %s)", [(address, m) for m in members])


@router.get("", response_model=list[ListOut])
def list_lists(domain: str | None = None, admin: UserOut = Depends(current_admin)) -> list[dict]:
    vis = visible_domains(admin)
    if domain:
        check_domain(admin, domain.lower())
        return db.fetch_all(SELECT + " WHERE l.domain = %s ORDER BY l.address", (domain.lower(),))
    if vis is not None:
        return db.fetch_all(SELECT + " WHERE l.domain = ANY(%s) ORDER BY l.domain, l.address", (vis,))
    return db.fetch_all(SELECT + " ORDER BY l.domain, l.address")


@router.post("", response_model=ListOut, status_code=201)
def create_list(body: ListIn, request: Request, admin: UserOut = Depends(current_admin)) -> dict:
    _, domain = split_address(body.address)
    check_domain(admin, domain)
    if not db.fetch_one("SELECT 1 FROM domains WHERE name = %s", (domain,)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"домен {domain} не найден")
    if db.fetch_one("SELECT 1 FROM lists WHERE address = %s UNION SELECT 1 FROM aliases WHERE address = %s "
                    "UNION SELECT 1 FROM mailboxes WHERE address = %s", (body.address,) * 3):
        raise HTTPException(status.HTTP_409_CONFLICT, f"адрес {body.address} уже занят")
    with db.tx() as conn:
        conn.execute("INSERT INTO lists (address, domain, name, ad_group, active) VALUES (%s, %s, %s, %s, %s)",
                     (body.address, domain, body.name, body.ad_group or None, body.active))
        set_members(conn, body.address, body.members)
        log(conn, admin.login, "list.create", body.address, body.model_dump(), client_ip(request))
    return _get(body.address)


@router.put("/{address}", response_model=ListOut)
def update_list(address: str, body: ListPatch, request: Request, admin: UserOut = Depends(current_admin)) -> dict:
    address = address.lower()
    cur = _get(address)
    check_domain(admin, cur["domain"])
    patch = body.model_dump(exclude_unset=True)
    members = patch.pop("members", None)
    if members is not None and (patch.get("ad_group") or (cur["ad_group"] and "ad_group" not in patch)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "состав рассылки, привязанной к группе AD, ведёт синхронизация")
    with db.tx() as conn:
        if patch:
            sets = ", ".join(f"{k} = %s" for k in patch)
            conn.execute(f"UPDATE lists SET {sets} WHERE address = %s", (*patch.values(), address))
        if members is not None:
            set_members(conn, address, members)
            patch["members"] = members
        log(conn, admin.login, "list.update", address, patch, client_ip(request))
    return _get(address)


@router.delete("/{address}", status_code=204)
def delete_list(address: str, request: Request, admin: UserOut = Depends(current_admin)) -> Response:
    address = address.lower()
    cur = _get(address)
    check_domain(admin, cur["domain"])
    with db.tx() as conn:
        conn.execute("DELETE FROM lists WHERE address = %s", (address,))
        log(conn, admin.login, "list.delete", address, {}, client_ip(request))
    return Response(status_code=204)
