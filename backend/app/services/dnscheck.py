"""Проверка DNS-записей домена для дашборда: MX, SPF, DKIM, DMARC.

Смотрим через системный резолвер (на VM это unbound). Ничего не меняем, только сравниваем с тем,
что ожидает сервер: MX должен указывать на MAIL_HOSTNAME, DKIM TXT — совпадать с ключом из базы.
Статусы: ok — всё совпадает; warn — запись есть, но не та; missing — записи нет; error — DNS не ответил.
"""
import dns.exception
import dns.resolver

from ..config import settings

TIMEOUT = 4.0


def _resolver() -> dns.resolver.Resolver:
    r = dns.resolver.Resolver()
    r.timeout = TIMEOUT
    r.lifetime = TIMEOUT * 2
    return r


def _txt(name: str) -> list[str] | None:
    """Все TXT-записи имени склеенными строками; None — ошибка DNS, [] — записей нет."""
    try:
        answers = _resolver().resolve(name, "TXT")
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return []
    except dns.exception.DNSException:
        return None
    return [b"".join(r.strings).decode("utf-8", "replace") for r in answers]


def check_mx(domain: str) -> dict:
    try:
        answers = _resolver().resolve(domain, "MX")
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return {"status": "missing", "records": [], "expected": settings.mail_hostname}
    except dns.exception.DNSException as e:
        return {"status": "error", "records": [], "expected": settings.mail_hostname, "detail": str(e)[:120]}
    records = sorted((r.preference, str(r.exchange).rstrip(".")) for r in answers)
    hosts = [h for _, h in records]
    status = "ok" if settings.mail_hostname.lower() in [h.lower() for h in hosts] else "warn"
    return {"status": status, "records": [f"{p} {h}" for p, h in records], "expected": settings.mail_hostname}


def check_spf(domain: str) -> dict:
    txts = _txt(domain)
    if txts is None:
        return {"status": "error", "record": None}
    spf = [t for t in txts if t.lower().startswith("v=spf1")]
    if not spf:
        return {"status": "missing", "record": None, "expected": f"v=spf1 mx a:{settings.mail_hostname} -all"}
    rec = spf[0]
    toks = [t.lower().lstrip("+") for t in rec.split()]
    # запись считаем рабочей, если в ней есть хоть один механизм, разрешающий наш сервер
    ok = any(t == "mx" or t == "a" or t.startswith(("a:", "ip4:", "ip6:", "include:")) for t in toks)
    return {"status": "ok" if ok and len(spf) == 1 else "warn", "record": rec,
            "expected": f"v=spf1 mx a:{settings.mail_hostname} -all"}


def check_dkim(domain: str, selector: str | None, public_key: str | None) -> dict:
    if not selector or not public_key:
        return {"status": "missing", "name": None, "found": False, "matches": False, "detail": "ключ не выпущен"}
    name = f"{selector}._domainkey.{domain}"
    txts = _txt(name)
    if txts is None:
        return {"status": "error", "name": name, "found": False, "matches": False}
    if not txts:
        return {"status": "missing", "name": name, "found": False, "matches": False}
    # сравниваем только p=..., пробелы и переносы в TXT игнорируем
    def pval(t: str) -> str:
        for part in t.replace(" ", "").split(";"):
            if part.startswith("p="):
                return part[2:]
        return ""
    matches = any(pval(t) == public_key.replace(" ", "") for t in txts)
    return {"status": "ok" if matches else "warn", "name": name, "found": True, "matches": matches}


def check_dmarc(domain: str) -> dict:
    txts = _txt(f"_dmarc.{domain}")
    expected = f"v=DMARC1; p=quarantine; rua=mailto:dmarc@{domain}"
    if txts is None:
        return {"status": "error", "record": None, "expected": expected}
    rec = next((t for t in txts if t.lower().replace(" ", "").startswith("v=dmarc1")), None)
    if not rec:
        return {"status": "missing", "record": None, "expected": expected}
    policy = ""
    for part in rec.replace(" ", "").split(";"):
        if part.startswith("p="):
            policy = part[2:].lower()
    return {"status": "ok" if policy in ("quarantine", "reject") else "warn", "record": rec, "expected": expected}
