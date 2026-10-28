"""Ограничение перебора паролей на входе (панель и кабинет): счётчики неудач в Redis.

Каждая проверка пароля — bind в AD, а неверные пароли копятся в политике блокировки учётки AD:
без ограничения любой из LAN мог бы заблокировать админу учётку. Поэтому считаем неудачи по логину
и по IP и отвечаем 429 ДО обращения к AD. Redis недоступен — не блокируем (иначе админ не войдёт при аварии).
"""
import redis
from fastapi import HTTPException, status

from ..config import settings

WINDOW_S = 15 * 60
LIMITS = {"login": 5, "ip": 20}


_redis: redis.Redis | None = None


def _client() -> redis.Redis:
    """Один клиент на процесс (у redis-py внутри пул соединений); при недоступном Redis ждём не дольше секунды."""
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(settings.redis_url, socket_timeout=1, socket_connect_timeout=1,
                                      decode_responses=True)
    return _redis


def _keys(scope: str, login: str, ip: str | None) -> dict[str, str]:
    return {"login": f"thr:{scope}:l:{login.lower()}", "ip": f"thr:{scope}:i:{ip or '-'}"}


def check(scope: str, login: str, ip: str | None) -> None:
    """429, если за последние 15 минут слишком много неудач по этому логину или с этого адреса."""
    try:
        r = _client()
        for kind, key in _keys(scope, login, ip).items():
            if int(r.get(key) or 0) >= LIMITS[kind]:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                    "слишком много неудачных попыток входа, повторите через 15 минут")
    except redis.RedisError:
        return


def fail(scope: str, login: str, ip: str | None) -> None:
    try:
        r = _client()
        for key in _keys(scope, login, ip).values():
            if r.incr(key) == 1:
                r.expire(key, WINDOW_S)
    except redis.RedisError:
        return


def reset(scope: str, login: str, ip: str | None) -> None:
    try:
        _client().delete(_keys(scope, login, ip)["login"])
    except redis.RedisError:
        return
