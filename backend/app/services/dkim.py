"""DKIM: генерация ключа, хранение в базе, выкладка в Redis для Rspamd.

Rspamd (local.d/dkim_signing.conf, use_redis = true) ищет:
    HGET DKIM_SELECTORS    <domain>             -> selector
    HGET DKIM_PRIVATE_KEYS <selector>.<domain>  -> PEM   (именно селектор.домен — проверено по логу rspamd 3.12)
"""
import base64

import psycopg
import redis
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from .. import db
from ..config import settings

KEYS_HASH = "DKIM_PRIVATE_KEYS"
SELECTORS_HASH = "DKIM_SELECTORS"


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def generate() -> tuple[str, str]:
    """(private PEM, public base64 DER) — RSA 2048."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()
    pub = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return priv, base64.b64encode(pub).decode()


def dns_record(domain: str, selector: str, public_b64: str) -> tuple[str, str]:
    return f"{selector}._domainkey.{domain}", f"v=DKIM1; k=rsa; p={public_b64}"


def _out(row: dict) -> dict:
    name, value = dns_record(row["domain"], row["selector"], row["public_key"])
    return {"selector": row["selector"], "dns_name": name, "dns_value": value, "created_at": row["created_at"]}


def get(domain: str) -> dict | None:
    row = db.fetch_one("SELECT domain, selector, public_key, created_at FROM dkim_keys WHERE domain = %s", (domain,))
    return _out(row) if row else None


def push(domain: str, selector: str, private_pem: str) -> None:
    r = _redis()
    with r.pipeline() as p:
        # старый ключ домена (другой селектор) убираем, чтобы в Redis не копились
        old = r.hget(SELECTORS_HASH, domain)
        if old and old != selector:
            p.hdel(KEYS_HASH, f"{old}.{domain}")
        p.hset(KEYS_HASH, f"{selector}.{domain}", private_pem)
        p.hset(SELECTORS_HASH, domain, selector)
        p.execute()


def create(conn: psycopg.Connection, domain: str, selector: str) -> dict:
    """Создаёт (или перевыпускает) ключ домена: база + Redis."""
    priv, pub = generate()
    row = conn.execute(
        "INSERT INTO dkim_keys (domain, selector, private_key, public_key) VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (domain) DO UPDATE SET selector = EXCLUDED.selector, private_key = EXCLUDED.private_key, "
        "public_key = EXCLUDED.public_key, created_at = now() "
        "RETURNING domain, selector, public_key, created_at", (domain, selector, priv, pub)).fetchone()
    push(domain, selector, priv)
    return _out(row)


def remove(conn: psycopg.Connection, domain: str) -> None:
    row = conn.execute("DELETE FROM dkim_keys WHERE domain = %s RETURNING selector", (domain,)).fetchone()
    if row:
        r = _redis()
        r.hdel(KEYS_HASH, f"{row['selector']}.{domain}")
        r.hdel(SELECTORS_HASH, domain)


def sync_all() -> int:
    """Перезаливает все ключи из базы в Redis (после пересоздания Redis). Возвращает число ключей."""
    rows = db.fetch_all("SELECT domain, selector, private_key FROM dkim_keys")
    for row in rows:
        push(row["domain"], row["selector"], row["private_key"])
    return len(rows)
