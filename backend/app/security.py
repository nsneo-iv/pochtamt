"""Хеши паролей в формате Dovecot и JWT для сессий панели."""
import base64
import datetime as dt
import hashlib
import hmac
import secrets

import bcrypt
import jwt

from .config import settings

DOVECOT_SCHEME = "{BLF-CRYPT}"


def hash_password(password: str) -> str:
    """bcrypt (cost 12) в виде, который Dovecot понимает без доп. настроек: {BLF-CRYPT}$2b$..."""
    return DOVECOT_SCHEME + bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()


def _verify_ssha512(password: str, stored: str) -> bool:
    """{SSHA512} (хеши, пришедшие из iRedMail): base64(sha512(пароль + соль) + соль)."""
    try:
        raw = base64.b64decode(stored[len("{SSHA512}"):], validate=True)
    except ValueError:
        return False
    digest, salt = raw[:64], raw[64:]
    return len(digest) == 64 and hmac.compare_digest(hashlib.sha512(password.encode() + salt).digest(), digest)


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith(DOVECOT_SCHEME):
        try:
            return bcrypt.checkpw(password.encode(), stored[len(DOVECOT_SCHEME):].encode())
        except ValueError:
            return False
    if stored.startswith("{SSHA512}"):
        return _verify_ssha512(password, stored)
    return False


def needs_rehash(stored: str) -> bool:
    """Хеш не в нашей схеме (импорт) — при успешном входе перехешировать в bcrypt."""
    return not stored.startswith(DOVECOT_SCHEME)


DUMMY_HASH = hash_password(secrets.token_hex(16))   # для выравнивания времени ответа при неизвестном ящике


def issue_token(login: str, typ: str = "admin") -> str:
    """typ: admin — панель, user — личный кабинет (sub = адрес ящика)."""
    now = dt.datetime.now(dt.timezone.utc)
    payload = {"sub": login, "typ": typ, "iat": now, "exp": now + dt.timedelta(minutes=settings.jwt_ttl_minutes)}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def read_token(token: str, typ: str = "admin") -> str | None:
    """Возвращает sub из токена нужного типа или None, если он невалиден/просрочен/другого типа."""
    try:
        p = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return p["sub"] if p.get("typ", "admin") == typ else None
