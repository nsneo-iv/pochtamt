"""Pydantic-схемы запросов и ответов (см. docs/api.md)."""
import datetime as dt
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")
LOCAL_RE = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,63}$")


def norm_domain(v: str) -> str:
    v = v.strip().lower().rstrip(".")
    if not DOMAIN_RE.match(v):
        raise ValueError(f"некорректное имя домена: {v!r}")
    return v


def norm_address(v: str, allow_catchall: bool = False) -> str:
    """Нормализует адрес: нижний регистр, проверка локальной части и домена. '@domain' — catch-all."""
    v = v.strip().lower()
    if "@" not in v:
        raise ValueError(f"адрес без домена: {v!r}")
    local, _, domain = v.rpartition("@")
    domain = norm_domain(domain)
    if local == "":
        if not allow_catchall:
            raise ValueError("пустая локальная часть адреса")
        return "@" + domain
    if not LOCAL_RE.match(local):
        raise ValueError(f"некорректная локальная часть адреса: {local!r}")
    return f"{local}@{domain}"


def split_address(address: str) -> tuple[str, str]:
    local, _, domain = address.rpartition("@")
    return local, domain


# ---------------------------------------------------------------- авторизация ----
class LoginIn(BaseModel):
    login: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=256)


class AuthConfigOut(BaseModel):
    ad_enabled: bool            # настроен ли Active Directory (вход доменной учёткой, ящики auth=ad, синхронизация)
    login_hint: str             # подсказка в поле логина


class UserOut(BaseModel):
    login: str
    display_name: str
    role: Literal["superadmin", "domain_admin"]
    domains: list[str] = []


class LoginOut(BaseModel):
    token: str
    user: UserOut


# ---------------------------------------------------------------- домены ----
class DomainIn(BaseModel):
    name: str
    description: str = ""
    max_mailboxes: int = Field(0, ge=0)
    max_quota_mb: int = Field(0, ge=0)
    active: bool = True

    _n = field_validator("name")(lambda v: norm_domain(v))


class DomainPatch(BaseModel):
    description: str | None = None
    max_mailboxes: int | None = Field(None, ge=0)
    max_quota_mb: int | None = Field(None, ge=0)
    active: bool | None = None


class DomainStats(BaseModel):
    mailboxes: int
    aliases: int
    lists: int
    used_mb: int


class DomainOut(BaseModel):
    name: str
    description: str
    max_mailboxes: int
    max_quota_mb: int
    active: bool
    created_at: dt.datetime
    stats: DomainStats | None = None


class DkimIn(BaseModel):
    selector: str = Field("mail", pattern=r"^[a-z0-9]([a-z0-9-]{0,30}[a-z0-9])?$")


class DkimOut(BaseModel):
    selector: str
    dns_name: str
    dns_value: str
    created_at: dt.datetime


# ---------------------------------------------------------------- ящики ----
class MailboxIn(BaseModel):
    address: str
    name: str = ""
    auth: Literal["local", "ad"] = "local"
    password: str | None = Field(None, min_length=8, max_length=256)
    ad_upn: str | None = None
    quota_mb: int = Field(1024, ge=0)
    active: bool = True

    _a = field_validator("address")(lambda v: norm_address(v))

    @field_validator("ad_upn")
    @classmethod
    def _upn(cls, v: str | None) -> str | None:
        return v.strip().lower() if v else None


class MailboxPatch(BaseModel):
    name: str | None = None
    auth: Literal["local", "ad"] | None = None
    ad_upn: str | None = None
    quota_mb: int | None = Field(None, ge=0)
    active: bool | None = None


class PasswordIn(BaseModel):
    password: str = Field(min_length=8, max_length=256)


class MePasswordIn(PasswordIn):
    """Смена пароля в кабинете: нужен и текущий пароль (украденный токен сессии пароль не меняет)."""
    current_password: str = Field(min_length=1, max_length=256)


class MailboxOut(BaseModel):
    address: str
    domain: str
    name: str
    auth: str
    ad_upn: str | None
    quota_mb: int
    used_mb: int = 0
    active: bool
    created_at: dt.datetime


# ---------------------------------------------------------------- алиасы ----
class AliasIn(BaseModel):
    address: str
    targets: list[str] = Field(min_length=1, max_length=100)
    description: str = ""
    active: bool = True

    _a = field_validator("address")(lambda v: norm_address(v, allow_catchall=True))

    @field_validator("targets")
    @classmethod
    def _t(cls, v: list[str]) -> list[str]:
        return sorted({norm_address(x) for x in v})


class AliasPatch(BaseModel):
    targets: list[str] | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    active: bool | None = None

    @field_validator("targets")
    @classmethod
    def _t(cls, v: list[str] | None) -> list[str] | None:
        return sorted({norm_address(x) for x in v}) if v is not None else None


class AliasOut(BaseModel):
    address: str
    domain: str
    targets: list[str]
    description: str
    active: bool
    created_at: dt.datetime


# ---------------------------------------------------------------- доменные алиасы ----
class DomainAliasIn(BaseModel):
    alias_domain: str
    target_domain: str

    _a = field_validator("alias_domain")(lambda v: norm_domain(v))
    _t = field_validator("target_domain")(lambda v: norm_domain(v))


class DomainAliasOut(BaseModel):
    alias_domain: str
    target_domain: str
    active: bool


# ---------------------------------------------------------------- рассылки ----
class ListIn(BaseModel):
    address: str
    name: str = ""
    members: list[str] = []
    ad_group: str | None = None
    active: bool = True

    _a = field_validator("address")(lambda v: norm_address(v))

    @field_validator("members")
    @classmethod
    def _m(cls, v: list[str]) -> list[str]:
        return sorted({norm_address(x) for x in v})


class ListPatch(BaseModel):
    name: str | None = None
    members: list[str] | None = None
    ad_group: str | None = None
    active: bool | None = None

    @field_validator("members")
    @classmethod
    def _m(cls, v: list[str] | None) -> list[str] | None:
        return sorted({norm_address(x) for x in v}) if v is not None else None


class ListOut(BaseModel):
    address: str
    domain: str
    name: str
    members: list[str]
    ad_group: str | None
    active: bool
    synced_at: dt.datetime | None


# ---------------------------------------------------------------- очередь, аудит, сводка ----
class QueueItem(BaseModel):
    id: str
    sender: str
    recipients: list[str]
    size: int
    arrival: dt.datetime
    reason: str = ""


class AuditItem(BaseModel):
    ts: dt.datetime
    actor: str
    action: str
    object: str
    details: dict


class AuditPage(BaseModel):
    items: list[AuditItem]
    total: int


class RspamdStats(BaseModel):
    scanned: int
    ham: int
    spam: int
    reject: int
    add_header: int
    greylist: int
    no_action: int
    learned: int
    connections: int
    uptime: int


class Stats(BaseModel):
    domains: int
    mailboxes: int
    aliases: int
    lists: int
    queue: int
    used_mb: int
    rspamd: RspamdStats | None = None   # только суперадмину; None — Rspamd недоступен


class SyncReport(BaseModel):
    create: list[str] = []
    update: list[str] = []
    disable: list[str] = []
    lists: list[str] = []
    errors: list[str] = []


# ---------------------------------------------------------------- дашборд домена ----
class DnsCheck(BaseModel):
    status: Literal["ok", "warn", "missing", "error"]
    record: str | None = None
    records: list[str] = []
    expected: str | None = None
    name: str | None = None
    found: bool | None = None
    matches: bool | None = None
    detail: str | None = None


class DomainDns(BaseModel):
    mx: DnsCheck
    spf: DnsCheck
    dkim: DnsCheck
    dmarc: DnsCheck


class DomainDashStats(BaseModel):
    mailboxes: int
    mailboxes_active: int
    mailboxes_ad: int
    aliases: int
    lists: int
    used_mb: int
    quota_mb: int          # сумма заданных квот ящиков
    unlimited: int         # ящиков без ограничения квоты


class TopMailbox(BaseModel):
    address: str
    name: str
    used_mb: int
    quota_mb: int
    percent: int           # 0 при безлимите
    active: bool


class DomainDashboard(BaseModel):
    """Сводка по одному домену: цифры, DKIM, проверка DNS, топ ящиков по месту, последние действия."""
    domain: DomainOut
    stats: DomainDashStats
    dkim: DkimOut | None
    dns: DomainDns
    top_mailboxes: list[TopMailbox]
    recent_audit: list[AuditItem]


# ---------------------------------------------------------------- спам-фильтр и антивирус ----
class FilterActions(BaseModel):
    greylist: float = Field(ge=0, le=100)
    add_header: float = Field(ge=0, le=100)
    reject: float = Field(ge=0, le=100)


class AntivirusInfo(BaseModel):
    available: bool
    daemon_active: bool
    engine_version: str | None = None
    db_version: str | None = None
    db_date: str | None = None
    signatures: int | None = None
    virus_score: float | None = None
    detail: str | None = None


class FilterOverview(BaseModel):
    stats: RspamdStats | None
    actions: FilterActions
    antivirus: AntivirusInfo


class SymbolRow(BaseModel):
    name: str
    score: float
    description: str
    group: str
    frequency: float


class SymbolSet(BaseModel):
    name: str = Field(pattern=r"^[A-Z0-9_]{2,64}$")
    score: float = Field(ge=-100, le=100)


class FilterList(BaseModel):
    id: str
    title: str
    description: str
    entries: list[str]
    count: int
    available: bool


class FilterListIn(BaseModel):
    entries: list[str]

    @field_validator("entries")
    @classmethod
    def _e(cls, v: list[str]) -> list[str]:
        out = []
        for x in v:
            x = x.strip().lower()
            if not x or x.startswith("#"):
                continue
            if not re.fullmatch(r"[a-z0-9@._+:\-/\[\]]{1,253}", x):
                raise ValueError(f"недопустимая запись: {x!r}")
            out.append(x)
        return sorted(set(out))


class HistorySymbol(BaseModel):
    name: str
    score: float


class HistoryRow(BaseModel):
    time: int
    ip: str
    user: str
    sender: str
    recipients: list[str]
    subject: str
    score: float
    required_score: float
    action: str
    size: int
    symbols: list[HistorySymbol]
    scan_time: float
    message_id: str


# ---------------------------------------------------------------- настройки сервера и домена ----
class DomainSettings(BaseModel):
    transport: str | None = Field(None, max_length=200)      # smtp:[relay.example.com]:25 или пусто
    bcc_address: str | None = None
    outbound_allowed: bool = True

    @field_validator("transport")
    @classmethod
    def _t(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        if not v:
            return None
        if not re.fullmatch(r"(smtp|relay|lmtp):(\[[A-Za-z0-9.\-]+\]|[A-Za-z0-9.\-]+)?(:\d{1,5})?", v):
            raise ValueError("транспорт в виде smtp:[host]:port")
        return v

    @field_validator("bcc_address")
    @classmethod
    def _b(cls, v: str | None) -> str | None:
        return norm_address(v) if v and v.strip() else None


class Smarthost(BaseModel):
    enabled: bool = False
    host: str = Field("", max_length=253)
    port: int = Field(25, ge=1, le=65535)
    user: str = Field("", max_length=200)
    password: str | None = Field(None, max_length=200)     # None в PUT = не менять; в GET не отдаётся
    password_set: bool = False

    @field_validator("host")
    @classmethod
    def _h(cls, v: str) -> str:
        v = v.strip().lower()
        if v and not DOMAIN_RE.match(v) and not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", v):
            raise ValueError("некорректный хост")
        return v


class TlsPolicyIn(BaseModel):
    domain: str
    policy: Literal["none", "may", "encrypt", "dane", "dane-only", "verify", "secure"]
    params: str = Field("", max_length=200, pattern=r"^[A-Za-z0-9=:.,_ \-]*$")
    comment: str = ""

    _d = field_validator("domain")(lambda v: norm_domain(v))


class TlsPolicyOut(TlsPolicyIn):
    updated_at: dt.datetime


class AccessRuleIn(BaseModel):
    kind: Literal["client", "sender", "recipient"]
    pattern: str = Field(min_length=1, max_length=253)
    action: Literal["OK", "REJECT", "DISCARD"]
    message: str = Field("", max_length=200, pattern=r"^[^\n\r]*$")
    comment: str = ""
    active: bool = True

    @field_validator("pattern")
    @classmethod
    def _p(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.fullmatch(r"[a-z0-9@._+\-:]{1,253}", v):
            raise ValueError("недопустимый шаблон")
        return v


class AccessRuleOut(AccessRuleIn):
    id: int
    created_at: dt.datetime


class HostParam(BaseModel):
    key: str
    value: str
    service: str
    type: str
    label: str
    group: str
    values: list[str] | None = None
    min: int | None = None
    max: int | None = None


class HostParamSet(BaseModel):
    value: str = Field(max_length=500)


# ---------------------------------------------------------------- настройки ящика, кабинет ----
class Autoreply(BaseModel):
    enabled: bool = False
    subject: str = Field("", max_length=200)
    body: str = Field("", max_length=4000)
    date_from: dt.date | None = None
    date_to: dt.date | None = None


class Forward(BaseModel):
    # пересылка пользователя: не более 10 адресов (иначе одно письмо = усилитель спама с чужим отправителем)
    targets: list[str] = Field(default_factory=list, max_length=10)
    keep_copy: bool = True

    @field_validator("targets")
    @classmethod
    def _t(cls, v: list[str]) -> list[str]:
        return sorted({norm_address(x) for x in v})


class MailboxSettingsOut(BaseModel):
    address: str
    mode: Literal["normal", "receive_only", "send_only", "internal"]
    autoreply: Autoreply
    forward: Forward
    sieve_custom: str
    bcc_address: str | None
    sieve_synced_at: dt.datetime | None
    sieve_error: str | None = None


class MailboxSettingsIn(BaseModel):
    mode: Literal["normal", "receive_only", "send_only", "internal"] | None = None
    autoreply: Autoreply | None = None
    forward: Forward | None = None
    sieve_custom: str | None = Field(None, max_length=20000)
    bcc_address: str | None = None

    @field_validator("bcc_address")
    @classmethod
    def _b(cls, v: str | None) -> str | None:
        return norm_address(v) if v and v.strip() else None


class MeLoginIn(BaseModel):
    address: str
    password: str = Field(min_length=1, max_length=256)

    _a = field_validator("address")(lambda v: norm_address(v))


class MeOut(BaseModel):
    address: str
    name: str
    domain: str
    auth: str
    quota_mb: int
    used_mb: int
    messages: int
    mode: str


class MeLoginOut(BaseModel):
    token: str
    me: MeOut


class MeSettingsIn(BaseModel):
    autoreply: Autoreply | None = None
    forward: Forward | None = None
    sieve_custom: str | None = Field(None, max_length=20000)
