"""Состояние и нагрузка сервера (только суперадмин)."""
from fastapi import APIRouter, Depends, Query

from ..deps import superadmin
from ..models import UserOut
from ..services import system

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/overview")
def overview(_: UserOut = Depends(superadmin)) -> dict:
    return system.overview()


@router.get("/history")
def history(hours: int = Query(24, ge=1, le=168), _: UserOut = Depends(superadmin)) -> dict:
    return {"points": system.history(hours)}
