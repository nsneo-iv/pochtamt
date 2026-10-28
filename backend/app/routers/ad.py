"""Синхронизация ящиков и рассылок с Active Directory (только суперадмин)."""
from fastapi import APIRouter, Depends, HTTPException, Request, status

from .. import db
from ..audit import log
from ..deps import client_ip, superadmin
from ..models import SyncReport, UserOut
from ..services import ad

router = APIRouter(prefix="/ad", tags=["ad"])


@router.get("/sync/preview", response_model=SyncReport)
def preview(_: UserOut = Depends(superadmin)) -> SyncReport:
    try:
        return ad.sync(apply=False)
    except ad.ADError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AD недоступен: {e}")


@router.post("/sync", response_model=SyncReport)
def apply(request: Request, admin: UserOut = Depends(superadmin)) -> SyncReport:
    try:
        report = ad.sync(apply=True, actor=admin.login)
    except ad.ADError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AD недоступен: {e}")
    with db.tx() as conn:
        log(conn, admin.login, "ad.sync", "ad", report.model_dump(), client_ip(request))
    return report
