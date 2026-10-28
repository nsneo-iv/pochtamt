#!/usr/bin/env python3
"""Разложить принятые с iRedMail Maildir'ы по хранилищу нового сервера. Запускать на новом сервере от root.

    sudo python3 place-maildirs.py /srv/migrate [--apply]

Ожидает в каталоге: mailboxes.tsv (из iredmail-export.sh) и vmail1/<maildir> (rsync со старого сервера).
Для каждого ящика: vmail1/<maildir>/Maildir -> /var/vmail/<домен>/<локальная часть>/Maildir, владелец vmail.
Индексы Dovecot 2.3 (dovecot.index*, dovecot.list.index*) не переносятся — Dovecot построит заново;
dovecot-uidlist и dovecot-uidvalidity остаются, поэтому клиенты не перекачивают письма.
Без --apply только печатает план. Уже существующий каталог назначения не перезаписывается.
"""
import csv
import os
import pwd
import re
import shutil
import sys

VMAIL = "/var/vmail"
ADDR = re.compile(r"^[A-Za-z0-9_%+-][A-Za-z0-9._%+-]*@[a-z0-9][a-z0-9.-]*$")   # без ведущей точки и «..»
SKIP_PREFIXES = ("dovecot.index", "dovecot.list.index", "dovecot.mailbox.log", "dovecot.thread")


def main() -> int:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src_root = sys.argv[1]
    apply = "--apply" in sys.argv[2:]
    uid = pwd.getpwnam("vmail").pw_uid
    gid = pwd.getpwnam("vmail").pw_gid
    with open(os.path.join(src_root, "mailboxes.tsv"), encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    total = 0
    for r in rows:
        addr = r["username"].strip().lower()
        if not ADDR.match(addr) or ".." in addr:
            print(f"пропуск (странный адрес): {addr!r}")
            continue
        local, domain = addr.split("@")
        rel = r["maildir"].strip("/")
        # защита от обхода каталога: путь из выгрузки должен остаться внутри vmail1
        src = os.path.realpath(os.path.join(src_root, "vmail1", rel, "Maildir"))
        base = os.path.realpath(os.path.join(src_root, "vmail1"))
        if not src.startswith(base + os.sep):
            print(f"пропуск (путь вне vmail1): {addr}")
            continue
        dst_home = os.path.join(VMAIL, domain, local)
        dst = os.path.join(dst_home, "Maildir")
        if not os.path.isdir(src):
            print(f"нет данных: {addr} ({rel})")
            continue
        if os.path.exists(dst):
            print(f"уже есть, пропуск: {dst}")
            continue
        size = sum(os.path.getsize(os.path.join(d, n)) for d, _, ns in os.walk(src) for n in ns)
        total += size
        print(f"{addr:34} {size / 1048576:9.1f} МБ  {src} -> {dst}")
        if not apply:
            continue
        for d, _, ns in os.walk(src):
            for n in ns:
                if n.startswith(SKIP_PREFIXES):
                    os.unlink(os.path.join(d, n))
        os.makedirs(os.path.join(VMAIL, domain), mode=0o750, exist_ok=True)
        os.makedirs(dst_home, mode=0o700, exist_ok=True)
        shutil.move(src, dst)
        # lchown: симлинк внутри Maildir не должен вести chown от root на чужой файл
        for d, dirs, ns in os.walk(dst_home):
            os.lchown(d, uid, gid)
            for n in ns:
                os.lchown(os.path.join(d, n), uid, gid)
        os.lchown(os.path.join(VMAIL, domain), uid, gid)
    print(f"итого: {total / 1048576:.1f} МБ" + ("" if apply else "  (предпросмотр; применить — с --apply)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
