"""Настройки сервера (только суперадмин): smarthost, TLS-политики, правила доступа SMTP, параметры Postfix/Dovecot."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from .. import db
from ..audit import log
from ..deps import client_ip, superadmin
from ..models import (AccessRuleIn, AccessRuleOut, HostParam, HostParamSet, Smarthost, TlsPolicyIn, TlsPolicyOut,
                      UserOut)
from ..services import agent, hostconf

router = APIRouter(prefix="/server", tags=["server"])

SMARTHOST_KEYS = ("smarthost_enabled", "smarthost_host", "smarthost_port", "smarthost_user", "smarthost_password")


def _settings(keys: tuple[str, ...]) -> dict:
    rows = db.fetch_all("SELECT key, value FROM settings WHERE key = ANY(%s)", (list(keys),))
    return {r["key"]: r["value"] for r in rows}


# ---------------------------------------------------------------- smarthost ----
@router.get("/smarthost", response_model=Smarthost)
def get_smarthost(_: UserOut = Depends(superadmin)) -> Smarthost:
    s = _settings(SMARTHOST_KEYS)
    return Smarthost(enabled=s.get("smarthost_enabled") == "true", host=s.get("smarthost_host", ""),
                     port=int(s.get("smarthost_port") or 25), user=s.get("smarthost_user", ""),
                     password=None, password_set=bool(s.get("smarthost_password")))


@router.put("/smarthost", response_model=Smarthost)
def set_smarthost(body: Smarthost, request: Request, admin: UserOut = Depends(superadmin)) -> Smarthost:
    if body.enabled and not body.host:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "укажите хост smarthost")
    vals = {"smarthost_enabled": "true" if body.enabled else "false", "smarthost_host": body.host,
            "smarthost_port": str(body.port), "smarthost_user": body.user}
    if body.password is not None:
        vals["smarthost_password"] = body.password
    with db.tx() as conn:
        for k, v in vals.items():
            conn.execute("INSERT INTO settings (key, value) VALUES (%s, %s) "
                         "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (k, v))
        log(conn, admin.login, "server.smarthost", "smarthost",
            {k: v for k, v in vals.items() if k != "smarthost_password"} | {"password_changed": body.password is not None},
            client_ip(request))
    return get_smarthost(admin)


# ---------------------------------------------------------------- TLS-политики ----
@router.get("/tls-policies", response_model=list[TlsPolicyOut])
def tls_policies(_: UserOut = Depends(superadmin)) -> list[dict]:
    return db.fetch_all("SELECT domain, policy, params, comment, updated_at FROM tls_policies ORDER BY domain")


@router.put("/tls-policies/{domain}", response_model=TlsPolicyOut)
def set_tls_policy(domain: str, body: TlsPolicyIn, request: Request, admin: UserOut = Depends(superadmin)) -> dict:
    domain = domain.lower()
    if body.domain != domain:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "домен в пути и теле не совпадает")
    with db.tx() as conn:
        row = conn.execute(
            "INSERT INTO tls_policies (domain, policy, params, comment) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (domain) DO UPDATE SET policy = EXCLUDED.policy, params = EXCLUDED.params, "
            "comment = EXCLUDED.comment RETURNING domain, policy, params, comment, updated_at",
            (domain, body.policy, body.params, body.comment)).fetchone()
        log(conn, admin.login, "server.tls_policy", domain, body.model_dump(), client_ip(request))
    return row


@router.delete("/tls-policies/{domain}", status_code=204)
def delete_tls_policy(domain: str, request: Request, admin: UserOut = Depends(superadmin)) -> Response:
    with db.tx() as conn:
        n = conn.execute("DELETE FROM tls_policies WHERE domain = %s", (domain.lower(),)).rowcount
        if not n:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "политика не найдена")
        log(conn, admin.login, "server.tls_policy.delete", domain.lower(), {}, client_ip(request))
    return Response(status_code=204)


# ---------------------------------------------------------------- правила доступа SMTP ----
COLS = "id, kind, pattern, action, message, comment, active, created_at"


@router.get("/access-rules", response_model=list[AccessRuleOut])
def access_rules(kind: str | None = None, _: UserOut = Depends(superadmin)) -> list[dict]:
    if kind:
        return db.fetch_all(f"SELECT {COLS} FROM access_rules WHERE kind = %s ORDER BY pattern", (kind,))
    return db.fetch_all(f"SELECT {COLS} FROM access_rules ORDER BY kind, pattern")


@router.post("/access-rules", response_model=AccessRuleOut, status_code=201)
def create_rule(body: AccessRuleIn, request: Request, admin: UserOut = Depends(superadmin)) -> dict:
    if db.fetch_one("SELECT 1 FROM access_rules WHERE kind = %s AND pattern = %s", (body.kind, body.pattern)):
        raise HTTPException(status.HTTP_409_CONFLICT, "такое правило уже есть")
    with db.tx() as conn:
        row = conn.execute(
            f"INSERT INTO access_rules (kind, pattern, action, message, comment, active) VALUES (%s, %s, %s, %s, %s, %s) "
            f"RETURNING {COLS}", (body.kind, body.pattern, body.action, body.message, body.comment, body.active)).fetchone()
        log(conn, admin.login, "server.access_rule.create", f"{body.kind}:{body.pattern}", body.model_dump(),
            client_ip(request))
    return row


@router.put("/access-rules/{rule_id}", response_model=AccessRuleOut)
def update_rule(rule_id: int, body: AccessRuleIn, request: Request, admin: UserOut = Depends(superadmin)) -> dict:
    with db.tx() as conn:
        row = conn.execute(
            f"UPDATE access_rules SET kind = %s, pattern = %s, action = %s, message = %s, comment = %s, active = %s "
            f"WHERE id = %s RETURNING {COLS}",
            (body.kind, body.pattern, body.action, body.message, body.comment, body.active, rule_id)).fetchone()
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "правило не найдено")
        log(conn, admin.login, "server.access_rule.update", f"{body.kind}:{body.pattern}", body.model_dump(),
            client_ip(request))
    return row


@router.delete("/access-rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, request: Request, admin: UserOut = Depends(superadmin)) -> Response:
    with db.tx() as conn:
        row = conn.execute("DELETE FROM access_rules WHERE id = %s RETURNING kind, pattern", (rule_id,)).fetchone()
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "правило не найдено")
        log(conn, admin.login, "server.access_rule.delete", f"{row['kind']}:{row['pattern']}", {}, client_ip(request))
    return Response(status_code=204)


# ---------------------------------------------------------------- параметры Postfix/Dovecot (через агент) ----
def _params_with_values(values: dict) -> list[dict]:
    out = []
    for key, p in hostconf.PARAMS.items():
        out.append({"key": key, "value": values.get(key, ""), "service": p["service"], "type": p["type"],
                    "label": p["label"], "group": p["group"], "values": p.get("values"),
                    "min": p.get("min"), "max": p.get("max")})
    return out


@router.get("/params", response_model=list[HostParam])
def params(_: UserOut = Depends(superadmin)) -> list[dict]:
    try:
        values = agent.host_params()
    except agent.AgentError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"агент недоступен: {e}")
    return _params_with_values(values)


@router.put("/params/{key}", response_model=HostParam)
def set_param(key: str, body: HostParamSet, request: Request, admin: UserOut = Depends(superadmin)) -> dict:
    p = hostconf.PARAMS.get(key)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "параметр не разрешён к изменению")
    try:
        value = hostconf.validate(key, body.value)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{key}: {e}")
    try:
        agent.host_param_set(p["service"], key, value)
        values = agent.host_params()
    except agent.AgentError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"не применено: {e}")
    with db.tx() as conn:
        log(conn, admin.login, "server.param", key, {"value": value, "service": p["service"]}, client_ip(request))
    return next(x for x in _params_with_values(values) if x["key"] == key)
