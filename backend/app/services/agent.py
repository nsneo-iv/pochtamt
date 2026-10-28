"""Клиент агента на почтовом хосте (agent/mail_agent.py): очередь Postfix и квоты Dovecot."""
import httpx

from ..config import settings


class AgentError(Exception):
    pass


def _client() -> httpx.Client:
    if not settings.agent_token:
        raise AgentError("AGENT_TOKEN не задан")
    return httpx.Client(base_url=settings.agent_url, headers={"X-Agent-Token": settings.agent_token}, timeout=30)


def _req(method: str, path: str, json: dict | None = None):
    try:
        with _client() as c:
            r = c.request(method, path, json=json)
    except httpx.HTTPError as e:
        raise AgentError(str(e))
    if r.status_code >= 400:
        raise AgentError(f"{r.status_code}: {r.text[:200]}")
    return r.json() if r.content else None


def queue() -> list[dict]:
    return _req("GET", "/queue")


def queue_flush() -> None:
    _req("POST", "/queue/flush")


def queue_delete(queue_id: str) -> None:
    if not queue_id.isalnum():
        raise AgentError("некорректный id письма")
    _req("DELETE", f"/queue/{queue_id}")


def quota() -> list[dict]:
    """[{address, bytes, messages}] по всем ящикам."""
    return _req("GET", "/quota")


def antivirus() -> dict:
    """Состояние ClamAV: версия движка и баз, число сигнатур, запущен ли clamd."""
    return _req("GET", "/antivirus")


def antivirus_update() -> None:
    """Внеплановая проверка обновлений баз (перезапуск freshclam)."""
    _req("POST", "/antivirus/update")


def host_params() -> dict:
    """Текущие значения глобальных параметров Postfix/Dovecot из реестра ({key: value})."""
    return _req("GET", "/settings")


def host_param_set(service: str, key: str, value: str) -> dict:
    return _req("POST", f"/settings/{service}/{key}", json={"value": value})


def system() -> dict:
    """Нагрузка и состояние хоста (см. agent/mail_agent.py system_info)."""
    return _req("GET", "/system")
