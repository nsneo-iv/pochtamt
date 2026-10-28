#!/bin/bash
# Выгрузка данных iRedMail (MariaDB, база vmail) в TSV-файлы для импорта в новый сервер.
# Запускать НА СТАРОМ сервере от root. Ничего не меняет — только читает.
#
#   bash iredmail-export.sh /root/iredmail-export
#
# Результат: каталог (права 0700, в файлах есть хеши паролей — не копировать куда попало):
#   domains.tsv, mailboxes.tsv, forwardings.tsv, alias_domain.tsv, domain_admins.tsv
# Дальше: rsync каталога и /var/vmail/vmail1 на новый сервер, затем `python -m app.cli import-iredmail`.
set -euo pipefail
export HOME=/root          # иначе mysql не найдёт /root/.my.cnf при запуске без login-shell
OUT="${1:?укажите каталог для выгрузки}"
umask 077
mkdir -p "$OUT"

q() { mysql --batch --raw -e "$2" > "$OUT/$1.tsv"; }

q domains       "SELECT domain, description, active, maxquota FROM vmail.domain"
q mailboxes     "SELECT username, password, name, domain, quota, active, maildir, storagebasedirectory, storagenode,
                        enablesmtp, enableimap, enabledeliver, isadmin FROM vmail.mailbox"
# пересылки и алиасы; строки address = forwarding — служебные «ящик сам себе», импорт их пропускает
q forwardings   "SELECT address, forwarding, domain, is_list, is_forwarding, is_alias, active FROM vmail.forwardings"
q alias_domain  "SELECT alias_domain, target_domain, active FROM vmail.alias_domain"
q domain_admins "SELECT username, domain, active FROM vmail.domain_admins"

echo "выгружено в $OUT:"
wc -l "$OUT"/*.tsv
