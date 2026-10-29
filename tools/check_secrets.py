"""Проверка, что в коммит не попали секреты. Ставится как pre-commit hook:

    python tools/check_secrets.py --install      # записать .git/hooks/pre-commit
    python tools/check_secrets.py                # проверить индекс (то, что уйдёт в коммит)
    python tools/check_secrets.py --all          # проверить все отслеживаемые файлы

Что ищется:
  * значения из всех .env репозитория (install/.env, backend/.env, agent/.env, ...), кроме несекретных ключей —
    имён пользователей, хостов, адресов, ID (суффиксы _USER, _HOST, _URL, _ID, _IP, _SERVER, _PORT, _PATH, _KEY-пути);
  * значения из файлов *-credentials.txt (строки вида «ключ: значение» / «ключ=значение», где ключ похож на пароль);
  * токены GitLab (glpat-…), блоки -----BEGIN … PRIVATE KEY-----;
  * слова «пароль»/«password» с явным значением в кавычках, содержащим буквы и цифры.
Если проверка сработала — вынесите значение в .env своей папки, а не обходите её.
"""
import glob
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ключи с такими окончаниями — не секреты (адреса, логины, идентификаторы, пути)
SAFE_SUFFIX = ("_USER", "_HOST", "_URL", "_URI", "_ID", "_IP", "_SERVER", "_PORT", "_PATH", "_PREFIXES", "_HOSTKEY",
               "_ROOT", "_MODE", "_EMAIL", "_UID", "_GID", "_NAME", "_PUBKEY", "JUMP_KEY", "TZ",
               # этот репозиторий: имена хостов, каталоги, сети, DN и пути к ключам — не секреты
               "_HOSTNAME", "_DIR", "_NETS", "_DN", "_SUFFIX", "_NETBIOS", "_CERT", "TLS_KEY", "SSH_KEY", "_DNS",
               "_FILE", "_ZONE", "_ZONES", "_TIMEZONE", "_WORKERS", "_MIRRORS", "_DOMAINS")
SKIP_EXT = (".pub", ".png", ".jpg", ".pdf", ".bin")


def _add(vals, k, v, src):
    v = v.strip().strip("\"'")
    if len(v) >= 6 and not k.upper().endswith(SAFE_SUFFIX) and not v.startswith("http") \
            and not re.fullmatch(r"[\d./:-]+", v):
        vals[v] = f"{k} ({src})"


def secret_values():
    """{значение: откуда} из всех .env и *-credentials.txt рабочей копии."""
    vals = {}
    for p in glob.glob(os.path.join(ROOT, "**", ".env"), recursive=True) + [os.path.join(ROOT, ".env")]:
        if not os.path.exists(p):
            continue
        rel = os.path.relpath(p, ROOT)
        for line in open(p, encoding="utf-8-sig"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                _add(vals, k.strip(), v, rel)
    for p in glob.glob(os.path.join(ROOT, "**", "*-credentials.txt"), recursive=True):
        rel = os.path.relpath(p, ROOT)
        for line in open(p, encoding="utf-8-sig", errors="replace"):
            m = re.match(r"\s*([^:=]*?(pass|парол|secret|token)[^:=]*)\s*[:=]\s*(\S+)\s*$", line, re.I)
            if m:
                _add(vals, "PASSWORD", m.group(3), rel)
    return vals


PATTERNS = [
    (re.compile(r"glpat-[A-Za-z0-9_.-]{15,}"), "токен GitLab"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "приватный ключ"),
    (re.compile(r"(парол[ьяю]|password|passwd|\$Pass\w*|\$\w*Pw)\s*[:=]?\s*[\"'`«]([A-Za-z0-9!@#$%^&*_./?+{}<>\[\];~-]{6,})[\"'`»]", re.I),
     "пароль в тексте"),
]
# строки, где «пароль» — это имя переменной/ключа, а не значение
PATTERN_SKIP = re.compile(r"Get-EnvValue|os\.environ|getenv|env\[|env\.get|\.env\b|\{\$|\$\{|macro|_PASSWORD\b|check_secrets|Read-Host")


def looks_like_password(v):
    return any(c.isdigit() for c in v) and any(c.isalpha() for c in v)


def staged_files():
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                         capture_output=True, text=True, encoding="utf-8", cwd=ROOT).stdout
    return [f for f in out.split("\n") if f]


def staged_content(f):
    return subprocess.run(["git", "show", ":" + f], capture_output=True, cwd=ROOT).stdout.decode("utf-8", "replace")


def scan(files, reader):
    vals = secret_values()
    hits = []
    for f in files:
        if f.endswith(SKIP_EXT):
            continue
        for i, line in enumerate(reader(f).split("\n"), 1):
            for v, src in vals.items():
                if v in line:
                    hits.append((f, i, f"значение {src}"))
            if PATTERN_SKIP.search(line):
                continue
            for rx, what in PATTERNS:
                m = rx.search(line)
                if m and (what != "пароль в тексте" or looks_like_password(m.group(2))):
                    hits.append((f, i, what))
    return hits


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if "--install" in sys.argv:
        hook = os.path.join(ROOT, ".git", "hooks", "pre-commit")
        open(hook, "w", encoding="utf-8", newline="\n").write(
            '#!/bin/sh\nexec python "$(git rev-parse --show-toplevel)/tools/check_secrets.py"\n')
        os.chmod(hook, 0o755)
        print("hook установлен:", hook)
        return 0
    if "--all" in sys.argv:
        files = subprocess.run(["git", "ls-files"], capture_output=True, text=True, encoding="utf-8", cwd=ROOT).stdout.split("\n")
        hits = scan([f for f in files if f], lambda f: open(os.path.join(ROOT, f), encoding="utf-8", errors="replace").read())
    else:
        hits = scan(staged_files(), staged_content)
    if hits:
        print("Похоже на секреты — коммит остановлен:", file=sys.stderr)
        for f, i, what in hits:
            print(f"  {f}:{i}: {what}", file=sys.stderr)
        print("Вынесите значение в .env своей папки (образец — .env.example).", file=sys.stderr)
        return 1
    print("секретов не найдено")
    return 0


if __name__ == "__main__":
    sys.exit(main())
