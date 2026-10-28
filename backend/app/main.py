"""Точка входа FastAPI: uvicorn app.main:app --host 127.0.0.1 --port 8000"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .config import settings
from .routers import (ad, aliases, audit, auth, domain_aliases, domains, filter, lists, mailboxes, me, queue, server,
                      stats, system)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.require_secrets()
    db.open_pool()
    yield
    db.close_pool()


# схема API и Swagger наружу не отдаём (описание — docs/api.md)
app = FastAPI(title="Pochtamt", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None,
              lifespan=lifespan)

if settings.cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])

API = "/api/v1"
for r in (auth, domains, mailboxes, aliases, domain_aliases, lists, ad, queue, audit, stats, filter, server, me, system):
    app.include_router(r.router, prefix=API)


@app.get(API + "/health", include_in_schema=False)
def health() -> dict:
    db.fetch_one("SELECT 1")
    return {"status": "ok"}
