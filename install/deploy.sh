#!/usr/bin/env bash
# ============================================================================
#  Доставка репозитория на сервер с рабочего ПК и запуск install.sh. Нужны VM_HOST, VM_USER, SSH_KEY в install/.env.
#      bash install/deploy.sh            # залить и установить
#      bash install/deploy.sh --sync     # только залить файлы (без install.sh)
#  .env-файлы (install/, backend/, agent/) заливаются вместе с репозиторием — заполните их заранее.
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."
# читаем .env построчно, не выполняя его как shell (в паролях бывают ; & $ и пробелы)
load_env() {
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in ''|'#'*) continue;; esac
        k=${line%%=*}; v=${line#*=}
        v=${v%\"}; v=${v#\"}; v=${v%\'}; v=${v#\'}
        export "$k=$v"
    done <"$1"
}
load_env install/.env
: "${VM_HOST:?}" "${VM_USER:?}" "${SSH_KEY:?}"
SSH_KEY=${SSH_KEY/#\~/$HOME}
SSH="ssh -i $SSH_KEY -o StrictHostKeyChecking=accept-new $VM_USER@$VM_HOST"

if [ ! -f frontend/dist/index.html ] && command -v npm >/dev/null; then
    echo "== собираю фронт"
    ( cd frontend && npm ci --silent && npm run build --silent )
fi

echo "== заливаю в $VM_USER@$VM_HOST:/opt/mail"
$SSH "sudo install -d -o $VM_USER /opt/mail"
# tar не удаляет файлы, которых больше нет в репозитории: каталоги шаблонов, которые приходят целиком, чистим заранее
$SSH "sudo rm -rf /opt/mail/install/nginx /opt/mail/install/fail2ban"
tar --exclude=.git --exclude='*/node_modules' --exclude='*/.venv' --exclude='install/out' \
    --exclude='__pycache__' --exclude='*.egg-info' -czf - . | $SSH "sudo tar -xzf - -C /opt/mail --no-same-owner"

# tar приносит права с ПК (0644) — файлы с секретами возвращаем в закрытый вид сразу, не дожидаясь install.sh
$SSH "sudo chown -R root:root /opt/mail/install; sudo chmod 0700 /opt/mail/install; sudo chmod 0600 /opt/mail/install/.env /opt/mail/agent/.env;       if id mailapp >/dev/null 2>&1; then sudo chown root:mailapp /opt/mail/backend/.env; fi;       sudo chmod 0640 /opt/mail/backend/.env"

if [ "${1:-}" != "--sync" ]; then
    echo "== install.sh"
    $SSH "sudo bash /opt/mail/install/install.sh"
fi
