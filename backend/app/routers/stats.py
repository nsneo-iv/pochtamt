"""Сводка для дашборда."""
from fastapi import APIRouter, Depends

from .. import db
from ..deps import current_admin, visible_domains
from ..models import Stats, UserOut
from ..services import agent, rspamd

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("", response_model=Stats)
def stats(admin: UserOut = Depends(current_admin)) -> Stats:
    vis = visible_domains(admin)
    flt = "" if vis is None else " WHERE domain = ANY(%s)"
    p = () if vis is None else (vis,)
    row = db.fetch_one(
        f"SELECT (SELECT count(*) FROM domains{flt.replace('domain =', 'name =')}) AS domains,"
        f" (SELECT count(*) FROM mailboxes{flt}) AS mailboxes,"
        f" (SELECT count(*) FROM aliases{flt}) AS aliases,"
        f" (SELECT count(*) FROM lists{flt}) AS lists,"
        f" (SELECT COALESCE(sum(u.bytes), 0) FROM mailbox_usage u JOIN mailboxes m ON m.address = u.address"
        f"{flt.replace('domain =', 'm.domain =')}) AS used_bytes",
        p * 5)
    queue = 0
    rs = None
    if vis is None:
        rs = rspamd.stat()
        try:
            queue = len(agent.queue())
        except agent.AgentError:
            queue = -1  # агент недоступен — фронт покажет прочерк
    return Stats(domains=row["domains"], mailboxes=row["mailboxes"], aliases=row["aliases"], lists=row["lists"],
                 queue=queue, used_mb=int(row["used_bytes"] // 1048576), rspamd=rs)
