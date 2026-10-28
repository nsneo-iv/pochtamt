"""Управление спам-фильтром и антивирусом (только суперадмин): пороги, веса, списки, история, ClamAV."""
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response, status

from .. import db
from ..audit import log
from ..deps import client_ip, superadmin
from ..models import (AntivirusInfo, FilterActions, FilterList, FilterListIn, FilterOverview, HistoryRow,
                      SymbolRow, SymbolSet, UserOut)
from ..services import agent, rspamd

router = APIRouter(prefix="/filter", tags=["filter"])


def _call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except rspamd.RspamdError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Rspamd недоступен: {e}")


def _antivirus() -> dict:
    info = {"available": False, "daemon_active": False, "engine_version": None, "db_version": None,
            "db_date": None, "signatures": None, "virus_score": None}
    try:
        info.update(agent.antivirus())
    except agent.AgentError as e:
        info["detail"] = str(e)
    try:
        # символ антивируса называется по имени правила в antivirus.conf: clamav -> CLAMAV
        sym = next((s for s in rspamd.get_symbols("CLAMAV") if s["name"] == "CLAMAV"), None)
        info["virus_score"] = sym["score"] if sym else None
    except rspamd.RspamdError:
        pass
    return info


@router.get("/overview", response_model=FilterOverview)
def overview(_: UserOut = Depends(superadmin)) -> dict:
    return {"stats": rspamd.stat(), "actions": _call(rspamd.get_actions), "antivirus": _antivirus()}


@router.get("/actions", response_model=FilterActions)
def get_actions(_: UserOut = Depends(superadmin)) -> dict:
    return _call(rspamd.get_actions)


@router.put("/actions", response_model=FilterActions)
def set_actions(body: FilterActions, request: Request, admin: UserOut = Depends(superadmin)) -> dict:
    if not (body.greylist < body.add_header < body.reject):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "пороги должны расти: greylist < add_header < reject")
    out = _call(rspamd.set_actions, body.model_dump())
    with db.tx() as conn:
        log(conn, admin.login, "filter.actions", "rspamd", body.model_dump(), client_ip(request))
    return out


@router.get("/symbols", response_model=list[SymbolRow])
def symbols(q: str | None = None, _: UserOut = Depends(superadmin)) -> list[dict]:
    return _call(rspamd.get_symbols, q)


@router.put("/symbols", status_code=204)
def set_symbols(items: list[SymbolSet], request: Request, admin: UserOut = Depends(superadmin)) -> Response:
    if not items:
        return Response(status_code=204)
    _call(rspamd.set_symbols, [i.model_dump() for i in items])
    with db.tx() as conn:
        log(conn, admin.login, "filter.symbols", "rspamd", {"symbols": [i.model_dump() for i in items]},
            client_ip(request))
    return Response(status_code=204)


@router.get("/lists", response_model=list[FilterList])
def lists(_: UserOut = Depends(superadmin)) -> list[dict]:
    return _call(rspamd.get_lists)


@router.put("/lists/{list_id}", response_model=FilterList)
def set_list(list_id: str, body: FilterListIn, request: Request, admin: UserOut = Depends(superadmin)) -> dict:
    if list_id not in rspamd.LISTS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"нет списка {list_id}")
    out = _call(rspamd.set_list, list_id, body.entries)
    with db.tx() as conn:
        log(conn, admin.login, "filter.list", list_id, {"count": len(body.entries)}, client_ip(request))
    return out


@router.get("/history", response_model=list[HistoryRow])
def history(limit: int = Query(100, ge=1, le=1000), action: str | None = None, q: str | None = None,
            _: UserOut = Depends(superadmin)) -> list[dict]:
    return _call(rspamd.history, limit, action, q)


@router.post("/learn/{kind}", status_code=204)
def learn(kind: str, request: Request, message: str = Body(..., media_type="text/plain"),
          admin: UserOut = Depends(superadmin)) -> Response:
    if kind not in ("spam", "ham"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "kind: spam | ham")
    _call(rspamd.learn, kind, message.encode("utf-8", "surrogateescape"))
    with db.tx() as conn:
        log(conn, admin.login, f"filter.learn.{kind}", "rspamd", {"size": len(message)}, client_ip(request))
    return Response(status_code=204)


@router.get("/antivirus", response_model=AntivirusInfo)
def antivirus(_: UserOut = Depends(superadmin)) -> dict:
    return _antivirus()


@router.post("/antivirus/update", status_code=202)
def antivirus_update(request: Request, admin: UserOut = Depends(superadmin)) -> Response:
    try:
        agent.antivirus_update()
    except agent.AgentError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"агент недоступен: {e}")
    with db.tx() as conn:
        log(conn, admin.login, "filter.antivirus.update", "clamav", {}, client_ip(request))
    return Response(status_code=202)
