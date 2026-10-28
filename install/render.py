#!/usr/bin/env python3
"""Подстановка значений из install/.env в шаблоны конфигов.

    python install/render.py            # результат в install/out/ (в git не попадает)
    python install/render.py --check    # только проверить, что все плейсхолдеры закрыты

Плейсхолдер в шаблоне — @KEY@; KEY берётся из install/.env (или переменной окружения с тем же именем).
Шаблоны: postfix/, dovecot/, rspamd/local.d/, db/roles.sql, db/schema_settings.sql,
install/nginx/, install/*.service, install/*.timer, install/sudoers-mail-agent, install/fail2ban/, install/nftables.conf.

Производные ключи (считаются здесь из .env, в .env их не пишут):
  ADMIN_ALLOW_RULES    — строки `allow <сеть>;` для nginx из ADMIN_ALLOW_NETS
  LAN_NETS_NFT / LAN_NETS_SPACE / LAN_NETS_COMMA — LAN_NETS для nftables, fail2ban и Rspamd
  DOVECOT_PASSDB_LDAP  — блок passdb ldap для Dovecot, если задан AD_LDAP_URI; иначе комментарий
"""
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "install", "out")
PH = re.compile(r"@([A-Z][A-Z0-9_]+)@")

TEMPLATES = [
    "postfix", "dovecot", "rspamd/local.d", "db/roles.sql",
    "install/nginx", "install/mail-backend.service", "install/mail-agent.service",
    "install/mail-usage-sync.service", "install/mail-usage-sync.timer",
    "install/mail-ad-sync.service", "install/mail-ad-sync.timer",
    "install/mail-system-sample.service", "install/mail-system-sample.timer",
    "install/sudoers-mail-agent", "install/fail2ban", "install/nftables.conf", "db/schema_settings.sql",
]
TEXT_EXT = (".cf", ".conf", ".inc", ".sql", ".php", ".service", ".timer", ".sieve", "")


def load_env() -> dict:
    env = {}
    path = os.path.join(ROOT, "install", ".env")
    if not os.path.exists(path):
        sys.exit("нет install/.env — скопируйте install/.env.example и заполните")
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip().strip("\"'")
    for k in list(env):
        if k in os.environ:
            env[k] = os.environ[k]
    # производные ключи: список сетей -> строки allow для nginx
    nets = env.get("ADMIN_ALLOW_NETS", "").split()
    env["ADMIN_ALLOW_RULES"] = "\n    ".join(f"allow {n};" for n in nets)
    lan = env.get("LAN_NETS", "").split()
    env["LAN_NETS_NFT"] = ", ".join(lan)
    env["LAN_NETS_SPACE"] = " ".join(lan)
    env["LAN_NETS_COMMA"] = ", ".join(lan)
    env["DOVECOT_PASSDB_LDAP"] = dovecot_passdb_ldap(env)
    return env


def dovecot_passdb_ldap(env: dict) -> str:
    """passdb ldap для ящиков auth = ad: только когда AD настроен (AD_LDAP_URI). Поля с пустым значением
    остаются как @KEY@ и будут пойманы проверкой незаполненных ключей."""
    if not env.get("AD_LDAP_URI"):
        return "# Active Directory не настроен (AD_LDAP_URI пуст): ящики только с локальными паролями (auth = local)"
    return """# 2) Active Directory (только для ящиков auth = ad): ищем учётку по UPN или mail, затем bind её паролем
ldap_uris = @AD_LDAP_URI@
ldap_auth_dn = @AD_BIND_USER@
ldap_auth_dn_password = @AD_BIND_PASSWORD@
ldap_base = @AD_BASE_DN@
ldap_version = 3
ldap_deref = never
ldap_scope = subtree
passdb ldap {
  bind = yes
  filter = (&(objectClass=user)(!(userAccountControl:1.2.840.113556.1.4.803:=2))(|(userPrincipalName=%{user})(mail=%{user})))
}"""


def render_file(src: str, dst: str, env: dict, missing: set) -> None:
    with open(src, encoding="utf-8") as f:
        text = f.read()

    def sub(m: re.Match) -> str:
        k = m.group(1)
        if k not in env or env[k] == "":
            missing.add(f"{k} ({os.path.relpath(src, ROOT)})")
            return m.group(0)
        return env[k]

    rendered = PH.sub(sub, text)
    rendered = PH.sub(sub, rendered)   # второй проход: производные блоки сами содержат плейсхолдеры
    if dst == os.devnull:
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(rendered)


def main() -> None:
    os.umask(0o077)   # в out лежат пароли ролей БД и AD — только владельцу
    check = "--check" in sys.argv
    env = load_env()
    missing: set = set()
    if not check and os.path.isdir(OUT):
        shutil.rmtree(OUT)
    for rel in TEMPLATES:
        src = os.path.join(ROOT, rel)
        if not os.path.exists(src):
            continue
        files = [src] if os.path.isfile(src) else [
            os.path.join(d, n) for d, _, ns in os.walk(src) for n in ns if not n.endswith(".md")]
        for f in files:
            if os.path.splitext(f)[1] not in TEXT_EXT:
                continue
            dst = os.path.join(OUT, os.path.relpath(f, ROOT))
            if check:
                dst = os.devnull
            render_file(f, dst, env, missing)
    if missing:
        print("не заполнены в install/.env:\n  " + "\n  ".join(sorted(missing)))
        sys.exit(1)
    print("ok" if check else f"готово: {OUT}")


if __name__ == "__main__":
    main()
