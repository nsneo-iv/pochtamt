"""Импорт данных iRedMail (выгрузка install/migrate/iredmail-export.sh) в базу нового сервера.

Переносятся: домены, ящики с хешами паролей как есть (Dovecot читает {SSHA512} и др. сам), пересылки/алиасы,
доменные алиасы. НЕ переносятся: админы iRedMail (админы панели — из AD), служебные строки «ящик сам себе».
Без apply функция ничего не пишет и возвращает отчёт.
"""
import csv
import os
from dataclasses import dataclass, field

from .. import db
from ..audit import log
from ..models import norm_address
from . import dkim

# схемы хешей, которые принимаем (Dovecot умеет их проверять); остальное — в отчёт и пропуск
_SCHEMES = ("{SSHA512}", "{SSHA256}", "{SSHA}", "{BLF-CRYPT}", "{SHA512-CRYPT}", "{SHA256-CRYPT}")
_WEAK = ("{SSHA}",)


@dataclass
class Report:
    domains: list[str] = field(default_factory=list)
    mailboxes: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    domain_aliases: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _read(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    # mysql --batch пишет NULL текстом
    return [{k: ("" if v == "NULL" else v) for k, v in r.items()} for r in rows]


def normalize_hash(raw: str) -> str | None:
    h = (raw or "").strip()
    if not h:
        return None
    if h.startswith("{"):
        head, _, tail = h.partition("}")
        scheme = head.upper() + "}"
        return scheme + tail if scheme in _SCHEMES else None
    if h.startswith(("$2a$", "$2b$", "$2y$")):
        return "{BLF-CRYPT}" + h
    if h.startswith("$6$"):
        return "{SHA512-CRYPT}" + h
    if h.startswith("$5$"):
        return "{SHA256-CRYPT}" + h
    return None


def run(directory: str, apply: bool, dkim_selector: str = "mail", actor: str = "cli") -> Report:
    rep = Report()
    domains = _read(os.path.join(directory, "domains.tsv"))
    boxes = _read(os.path.join(directory, "mailboxes.tsv"))
    fwds = _read(os.path.join(directory, "forwardings.tsv"))
    alias_domains = _read(os.path.join(directory, "alias_domain.tsv"))

    have_domains = {r["name"] for r in db.fetch_all("SELECT name::text AS name FROM domains")}
    have_boxes = {r["address"] for r in db.fetch_all("SELECT address::text AS address FROM mailboxes")}
    have_aliases = {r["address"] for r in db.fetch_all("SELECT address::text AS address FROM aliases")}
    have_lists = {r["address"] for r in db.fetch_all("SELECT address::text AS address FROM lists")}

    new_domains = [d for d in domains if d["domain"].lower() not in have_domains and d["domain"] != "ALL"]
    for d in new_domains:
        rep.domains.append(d["domain"].lower())

    all_domains = have_domains | set(rep.domains)
    new_boxes = []
    for b in boxes:
        try:
            addr = norm_address(b["username"])
        except ValueError:
            rep.skipped.append(f"{b['username']!r}: некорректный адрес")
            continue
        domain = addr.rpartition("@")[2]
        if addr in have_boxes:
            rep.skipped.append(f"{addr}: уже есть")
            continue
        if domain not in all_domains:
            rep.skipped.append(f"{addr}: домен {domain} не импортирован")
            continue
        pw = normalize_hash(b["password"])
        if pw is None:
            rep.skipped.append(f"{addr}: неизвестная схема хеша пароля")
            continue
        if pw.startswith(_WEAK):
            rep.warnings.append(f"{addr}: слабый хеш {{SSHA}} — сменить пароль после переезда")
        if b.get("enabledeliver") == "0" or b.get("enableimap") == "0":
            rep.warnings.append(f"{addr}: в iRedMail отключены доставка/IMAP — на новом сервере включено")
        local = addr.split("@")[0]
        quota = int(b.get("quota") or 0)       # в iRedMail — МБ, 0 = без ограничения
        new_boxes.append((addr, domain, local, b.get("name", ""), pw, quota, b.get("active") == "1"))
        rep.mailboxes.append(addr)

    # пересылки: группируем по адресу. Строка address = forwarding у ящика значит «оставлять копию в ящике»
    # (iRedMail так кодирует keep-copy); у самого ящика без других целей это служебная запись — её пропускаем
    groups: dict[str, list[str]] = {}
    keep_copy: set[str] = set()
    for f in fwds:
        a, t = f["address"].strip().lower(), f["forwarding"].strip().lower()
        if not a or f.get("active") == "0":
            continue
        if a == t:
            keep_copy.add(a)
            continue
        try:
            t = norm_address(t)
        except ValueError:
            rep.warnings.append(f"{a}: цель пересылки {t!r} некорректна, пропущена")
            continue
        groups.setdefault(a, []).append(t)
    new_aliases = []
    for a, targets in groups.items():
        dom = a.rsplit("@", 1)[-1]
        if a in have_aliases or a in have_lists:
            rep.skipped.append(f"{a}: алиас уже есть")
        elif dom not in all_domains:
            rep.skipped.append(f"{a}: домен не импортирован")
        else:
            if (a in have_boxes or a in rep.mailboxes) and a in keep_copy:
                # пересылка с ящика с копией: в новой модели — сам ящик среди целей алиаса
                targets = list(dict.fromkeys([a] + targets))
            new_aliases.append((a, dom, targets))
            rep.aliases.append(a)

    new_alias_domains = []
    for r in alias_domains:
        if r.get("active") == "0":
            continue
        new_alias_domains.append((r["alias_domain"].lower(), r["target_domain"].lower()))
        rep.domain_aliases.append(r["alias_domain"].lower())

    if not apply:
        return rep

    with db.tx() as conn:
        for d in new_domains:
            name = d["domain"].lower()
            conn.execute("INSERT INTO domains (name, description, active) VALUES (%s, %s, %s)",
                         (name, d.get("description", "") or "импорт из iRedMail", d.get("active") == "1"))
            dkim.create(conn, name, dkim_selector)
            log(conn, actor, "migrate.domain", name, {"source": "iredmail"})
        for addr, domain, local, name, pw, quota, active in new_boxes:
            conn.execute(
                "INSERT INTO mailboxes (address, domain, local_part, name, auth, password, quota_mb, active) "
                "VALUES (%s, %s, %s, %s, 'local', %s, %s, %s)", (addr, domain, local, name, pw, quota, active))
            log(conn, actor, "migrate.mailbox", addr, {"source": "iredmail", "quota_mb": quota})
        for addr, dom, targets in new_aliases:
            conn.execute("INSERT INTO aliases (address, domain, description) VALUES (%s, %s, 'импорт из iRedMail')",
                         (addr, dom))
            for t in targets:
                conn.execute("INSERT INTO alias_targets (alias, target) VALUES (%s, %s)", (addr, t))
            log(conn, actor, "migrate.alias", addr, {"targets": len(targets)})
        for a, t in new_alias_domains:
            conn.execute("INSERT INTO domain_aliases (alias_domain, target_domain) VALUES (%s, %s) "
                         "ON CONFLICT DO NOTHING", (a, t))
    return rep


def import_dkim(directory: str, selector: str, apply: bool, actor: str = "cli") -> list[str]:
    """Ключи DKIM старого сервера (<домен>.pem) → dkim_keys и Redis, с прежним селектором.
    Так подписи остаются валидными без изменения DNS: TXT `<selector>._domainkey.<домен>` уже опубликован."""
    import base64
    import glob

    from cryptography.hazmat.primitives import serialization

    out = []
    domains = {r["name"] for r in db.fetch_all("SELECT name::text AS name FROM domains")}
    for path in sorted(glob.glob(os.path.join(directory, "*.pem"))):
        domain = os.path.basename(path)[:-4].lower()
        if domain not in domains:
            out.append(f"{domain}: домена нет в базе, пропуск")
            continue
        with open(path, "rb") as f:
            pem = f.read()
        key = serialization.load_pem_private_key(pem, password=None)
        pub = base64.b64encode(key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).decode()
        bits = key.key_size
        out.append(f"{domain}: ключ RSA-{bits}, селектор {selector}" + (" — слабый, перевыпустить" if bits < 2048 else ""))
        if apply:
            with db.tx() as conn:
                conn.execute(
                    "INSERT INTO dkim_keys (domain, selector, private_key, public_key) VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (domain) DO UPDATE SET selector = EXCLUDED.selector, "
                    "private_key = EXCLUDED.private_key, public_key = EXCLUDED.public_key, created_at = now()",
                    (domain, selector, pem.decode(), pub))
                log(conn, actor, "migrate.dkim", domain, {"selector": selector, "bits": bits})
            dkim.push(domain, selector, pem.decode())
    return out
