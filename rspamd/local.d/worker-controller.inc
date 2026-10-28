# веб-интерфейс и API Rspamd: только localhost; наружу — через nginx панели с ограничением по сети.
# Пароль — хеш из `rspamadm pw`, его подставляет render.py (RSPAMD_PASSWORD_HASH)
bind_socket = "127.0.0.1:11334";
password = "@RSPAMD_PASSWORD_HASH@";
enable_password = "@RSPAMD_PASSWORD_HASH@";
secure_ip = "127.0.0.1";
