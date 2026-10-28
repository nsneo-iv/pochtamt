"""Очередь Postfix через агент на почтовом хосте (только суперадмин)."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from .. import db
from ..audit import log
from ..deps import client_ip, superadmin
from ..models import QueueItem, UserOut
from ..services import agent

router = APIRouter(prefix="/queue", tags=["queue"])


def _call(fn, *a):
    try:
        return fn(*a)
    except agent.AgentError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"агент недоступен: {e}")


@router.get("", response_model=list[QueueItem])
def list_queue(_: UserOut = Depends(superadmin)) -> list[dict]:
    return _call(agent.queue)


@router.post("/flush", status_code=204)
def flush(request: Request, admin: UserOut = Depends(superadmin)) -> Response:
    _call(agent.queue_flush)
    with db.tx() as conn:
        log(conn, admin.login, "queue.flush", "queue", {}, client_ip(request))
    return Response(status_code=204)


@router.delete("/{queue_id}", status_code=204)
def delete(queue_id: str, request: Request, admin: UserOut = Depends(superadmin)) -> Response:
    _call(agent.queue_delete, queue_id)
    with db.tx() as conn:
        log(conn, admin.login, "queue.delete", queue_id, {}, client_ip(request))
    return Response(status_code=204)
