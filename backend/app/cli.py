"""Служебные команды бэкенда (запускать из backend/ с активированным venv):

    python -m app.cli init-db                      # применить db/schema.sql
    python -m app.cli admin-add admin superadmin --password          # локальный админ (пароль спросит)
    python -m app.cli admin-add user@corp.local superadmin           # админ из AD (пароль проверяет AD)
    python -m app.cli admin-add user@corp.local domain_admin --domains example.com,example.org
    python -m app.cli admin-password admin         # сменить локальный пароль админа
    python -m app.cli admin-list
    python -m app.cli dkim-sync                    # перезалить ключи DKIM в Redis
    python -m app.cli ad-sync [--apply]            # синхронизация с AD (без --apply только показать)
    python -m app.cli usage-sync                   # обновить занятое место ящиков из doveadm (через агент)
    python -m app.cli system-sample                # записать выборку нагрузки (таймер раз в 5 минут)
    python -m app.cli import-iredmail DIR [--apply]  # импорт доменов/ящиков/алиасов из выгрузки iRedMail
    python -m app.cli import-dkim DIR --selector dkim [--apply]  # ключи DKIM старого сервера (<домен>.pem)
"""
import argparse
import getpass
import os
import sys

from . import db
from .config import settings
from .audit import log
from .security import hash_password
from .services import ad, dkim, migrate_iredmail, system as system_svc, usage

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def cmd_init_db(_: argparse.Namespace) -> None:
    path = os.path.join(ROOT, "db", "schema.sql")
    with open(path, encoding="utf-8") as f, db.tx() as conn:
        conn.execute(f.read())
    print(f"схема применена: {path}")


def _read_password() -> str:
    """Пароль с терминала (дважды) или одной строкой со stdin, если он не терминал."""
    if not sys.stdin.isatty():
        pw = sys.stdin.readline().rstrip("\r\n")
    else:
        pw = getpass.getpass("Пароль: ")
        if pw != getpass.getpass("Ещё раз: "):
            sys.exit("пароли не совпадают")
    if len(pw) < 12:
        sys.exit("пароль админа — не короче 12 символов")
    return pw


def cmd_admin_add(a: argparse.Namespace) -> None:
    login = ad.normalize_login(a.login)
    domains = [d.strip().lower() for d in (a.domains or "").split(",") if d.strip()]
    if a.role == "domain_admin" and not domains:
        sys.exit("для domain_admin укажите --domains")
    if not a.password and not ad.enabled():
        sys.exit("Active Directory не настроен: задайте локальный пароль (--password)")
    pw_hash = hash_password(_read_password()) if a.password else None
    with db.tx() as conn:
        conn.execute("INSERT INTO admins (login, role, active, password_hash) VALUES (%s, %s, true, %s) "
                     "ON CONFLICT (login) DO UPDATE SET role = EXCLUDED.role, active = true, "
                     "password_hash = COALESCE(EXCLUDED.password_hash, admins.password_hash)", (login, a.role, pw_hash))
        conn.execute("DELETE FROM admin_domains WHERE login = %s", (login,))
        for d in domains:
            conn.execute("INSERT INTO admin_domains (login, domain) VALUES (%s, %s)", (login, d))
        log(conn, "cli", "admin.add", login, {"role": a.role, "domains": domains, "local_password": bool(pw_hash)})
    print(f"админ {login}: {a.role} {domains or ''} {'(локальный пароль)' if pw_hash else '(пароль проверяет AD)'}")


def cmd_admin_password(a: argparse.Namespace) -> None:
    login = ad.normalize_login(a.login)
    if not db.fetch_one("SELECT 1 FROM admins WHERE login = %s", (login,)):
        sys.exit(f"админа {login} нет")
    pw_hash = hash_password(_read_password())
    with db.tx() as conn:
        conn.execute("UPDATE admins SET password_hash = %s WHERE login = %s", (pw_hash, login))
        log(conn, "cli", "admin.password", login, {})
    print(f"пароль админа {login} обновлён")


def cmd_admin_list(_: argparse.Namespace) -> None:
    for r in db.fetch_all("SELECT a.login, a.role, a.active, "
                          "(SELECT string_agg(domain, ',') FROM admin_domains d WHERE d.login = a.login) AS domains "
                          "FROM admins a ORDER BY login"):
        print(f"{r['login']:40} {r['role']:13} {'вкл' if r['active'] else 'выкл':5} {r['domains'] or ''}")


def cmd_dkim_sync(_: argparse.Namespace) -> None:
    print(f"ключей DKIM в Redis: {dkim.sync_all()}")


def cmd_ad_sync(a: argparse.Namespace) -> None:
    if not ad.enabled():
        print("Active Directory не настроен (AD_LDAP_URI пуст) — синхронизация пропущена")
        return
    rep = ad.sync(apply=a.apply, actor="cli")
    for k in ("create", "update", "disable", "lists", "errors"):
        items = getattr(rep, k)
        if items:
            print(f"{k}: {len(items)}")
            for x in items:
                print("   ", x)
    if not a.apply:
        print("(предпросмотр; применить — с --apply)")


def cmd_usage_sync(_: argparse.Namespace) -> None:
    print(f"обновлено ящиков: {usage.sync()}")


def cmd_system_sample(_: argparse.Namespace) -> None:
    print("выборка записана" if system_svc.sample() else "агент недоступен, выборка пропущена")


def cmd_import_iredmail(a: argparse.Namespace) -> None:
    rep = migrate_iredmail.run(a.dir, apply=a.apply, dkim_selector=a.selector)
    for k in ("domains", "mailboxes", "aliases", "domain_aliases", "skipped", "warnings"):
        items = getattr(rep, k)
        print(f"{k}: {len(items)}")
        for x in items:
            print("   ", x)
    if not a.apply:
        print("(предпросмотр; применить — с --apply)")


def cmd_import_dkim(a: argparse.Namespace) -> None:
    for line in migrate_iredmail.import_dkim(a.dir, a.selector, apply=a.apply):
        print(line)
    if not a.apply:
        print("(предпросмотр; применить — с --apply)")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db").set_defaults(fn=cmd_init_db)
    s = sub.add_parser("admin-add")
    s.add_argument("login")
    s.add_argument("role", choices=["superadmin", "domain_admin"])
    s.add_argument("--domains", help="через запятую, для domain_admin")
    s.add_argument("--password", action="store_true", help="локальный пароль (спросит; без AD обязателен)")
    s.set_defaults(fn=cmd_admin_add)
    s = sub.add_parser("admin-password")
    s.add_argument("login")
    s.set_defaults(fn=cmd_admin_password)
    sub.add_parser("admin-list").set_defaults(fn=cmd_admin_list)
    sub.add_parser("dkim-sync").set_defaults(fn=cmd_dkim_sync)
    s = sub.add_parser("ad-sync")
    s.add_argument("--apply", action="store_true")
    s.set_defaults(fn=cmd_ad_sync)
    sub.add_parser("usage-sync").set_defaults(fn=cmd_usage_sync)
    sub.add_parser("system-sample").set_defaults(fn=cmd_system_sample)
    s = sub.add_parser("import-iredmail")
    s.add_argument("dir", help="каталог с TSV из install/migrate/iredmail-export.sh")
    s.add_argument("--selector", default="mail", help="селектор DKIM для новых доменов")
    s.add_argument("--apply", action="store_true")
    s.set_defaults(fn=cmd_import_iredmail)
    s = sub.add_parser("import-dkim")
    s.add_argument("dir", help="каталог с <домен>.pem")
    s.add_argument("--selector", required=True, help="селектор, под которым ключ опубликован в DNS (iRedMail: dkim)")
    s.add_argument("--apply", action="store_true")
    s.set_defaults(fn=cmd_import_dkim)
    a = p.parse_args()
    settings.require_secrets()
    db.open_pool()
    try:
        a.fn(a)
    finally:
        db.close_pool()


if __name__ == "__main__":
    main()
