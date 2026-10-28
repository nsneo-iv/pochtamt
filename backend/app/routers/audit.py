"""Журнал действий."""
from fastapi import APIRouter, Depends, Query

from .. import db
from ..deps import current_admin, visible_domains
from ..models import AuditPage, UserOut

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=AuditPage)
def audit(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
          actor: str | None = None, object: str | None = None,
          admin: UserOut = Depends(current_admin)) -> AuditPage:
    where, params = [], []
    if actor:
        where.append("actor ILIKE %s")
        params.append(f"%{actor}%")
    if object:
        where.append("object ILIKE %s")
        params.append(f"%{object}%")
    vis = visible_domains(admin)
    if vis is not None:
        # доменный админ видит только записи по объектам своих доменов (адрес или сам домен)
        where.append("(object = ANY(%s) OR split_part(object, '@', 2) = ANY(%s))")
        params += [vis, vis]
    w = (" WHERE " + " AND ".join(where)) if where else ""
    total = db.fetch_one(f"SELECT count(*) AS n FROM audit_log{w}", params)["n"]
    items = db.fetch_all(f"SELECT ts, actor, action, object, details FROM audit_log{w} "
                         f"ORDER BY ts DESC, id DESC LIMIT %s OFFSET %s", [*params, limit, offset])
    return AuditPage(items=items, total=total)
