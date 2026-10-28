"""Реестр глобальных параметров Postfix/Dovecot, которые можно менять из панели.

Значение проверяется здесь и ещё раз в помощнике агента на хосте (agent/apply_settings.py — тот же список).
Ключи, которых нет в реестре, изменить нельзя ни через API, ни через агент.
"""
import re

PARAMS: dict[str, dict] = {
    # ---- Postfix ----
    "message_size_limit": {"service": "postfix", "type": "int", "min": 1_048_576, "max": 209_715_200,
                           "label": "Максимальный размер письма, байт", "group": "Приём и отправка"},
    "smtpd_client_connection_rate_limit": {"service": "postfix", "type": "int", "min": 0, "max": 10000,
                                           "label": "Соединений с одного IP за период anvil", "group": "Лимиты"},
    "smtpd_client_message_rate_limit": {"service": "postfix", "type": "int", "min": 0, "max": 100000,
                                        "label": "Писем с одного IP за период anvil", "group": "Лимиты"},
    "smtpd_client_recipient_rate_limit": {"service": "postfix", "type": "int", "min": 0, "max": 100000,
                                          "label": "Получателей с одного IP за период anvil", "group": "Лимиты"},
    "anvil_rate_time_unit": {"service": "postfix", "type": "re", "re": r"^\d{1,5}s$",
                             "label": "Период подсчёта лимитов (например 60s)", "group": "Лимиты"},
    "smtpd_banner": {"service": "postfix", "type": "re", "re": r"^\$myhostname( [A-Za-z0-9 ._-]{0,80})?$",
                     "label": "Баннер SMTP (начинается с $myhostname)", "group": "Приём и отправка"},
    "smtpd_tls_protocols": {"service": "postfix", "type": "enum", "values": [">=TLSv1.2", ">=TLSv1.3"],
                            "label": "Версии TLS для входящих (например >=TLSv1.2)", "group": "TLS"},
    "smtpd_tls_mandatory_protocols": {"service": "postfix", "type": "enum", "values": [">=TLSv1.2", ">=TLSv1.3"],
                                      "label": "Версии TLS для обязательного TLS (587/465)", "group": "TLS"},
    "smtp_tls_security_level": {"service": "postfix", "type": "enum", "values": ["may", "encrypt", "dane"],
                                "label": "TLS для исходящих по умолчанию", "group": "TLS"},
    "mynetworks": {"service": "postfix", "type": "re", "re": r"^([0-9a-fA-F:.\[\]/]+)(,? +[0-9a-fA-F:.\[\]/]+)*$",
                   "label": "Доверенные сети (без авторизации и проверок)", "group": "Приём и отправка"},
    "maximal_queue_lifetime": {"service": "postfix", "type": "re", "re": r"^\d{1,4}[smhdw]$",
                               "label": "Сколько держать письмо в очереди (например 5d)", "group": "Очередь"},
    "bounce_queue_lifetime": {"service": "postfix", "type": "re", "re": r"^\d{1,4}[smhdw]$",
                              "label": "Сколько держать отчёты о недоставке (например 5d)", "group": "Очередь"},
    "disable_vrfy_command": {"service": "postfix", "type": "enum", "values": ["yes", "no"],
                             "label": "Запретить команду VRFY", "group": "Приём и отправка"},
    "smtpd_helo_required": {"service": "postfix", "type": "enum", "values": ["yes", "no"],
                            "label": "Требовать HELO/EHLO", "group": "Приём и отправка"},
    # ---- Dovecot ----
    "mail_max_userip_connections": {"service": "dovecot", "type": "int", "min": 1, "max": 1000,
                                    "label": "IMAP-соединений одного пользователя с одного IP", "group": "IMAP"},
    "auth_failure_delay": {"service": "dovecot", "type": "re", "re": r"^\d{1,3} secs$",
                           "label": "Задержка после неверного пароля (например 2 secs)", "group": "IMAP"},
    "imap_idle_notify_interval": {"service": "dovecot", "type": "re", "re": r"^\d{1,3} mins$",
                                  "label": "Интервал уведомлений IDLE (например 2 mins)", "group": "IMAP"},
    "quota_exceeded_message": {"service": "dovecot", "type": "re", "re": r"^[\w .,!?:/()-]{1,200}$",
                               "label": "Сообщение при переполнении ящика", "group": "Квоты"},
    "lmtp_rcpt_check_quota": {"service": "dovecot", "type": "enum", "values": ["yes", "no"],
                              "label": "Отклонять письмо при приёме, если ящик полон", "group": "Квоты"},
}


def _check_nets(v: str) -> None:
    """mynetworks: только loopback и частные сети не шире /16 (v4) и /64 (v6) (копия проверки в agent/apply_settings.py)."""
    import ipaddress
    for tok in re.split(r"[,\s]+", v.strip()):
        if not tok:
            continue
        try:
            net = ipaddress.ip_network(tok.replace("[", "").replace("]", ""), strict=False)
        except ValueError:
            raise ValueError(f"mynetworks: {tok!r} - не адрес и не сеть")
        if not (net.is_loopback or net.is_private):
            raise ValueError(f"mynetworks: {tok} - только частные сети и loopback")
        if net.prefixlen < (16 if net.version == 4 else 64) and not net.is_loopback:
            raise ValueError(f"mynetworks: {tok} - сеть слишком широкая (не шире /16)")


def validate(key: str, value: str) -> str:
    """Возвращает нормализованное значение или бросает ValueError."""
    p = PARAMS.get(key)
    if not p:
        raise ValueError(f"параметр {key} не разрешён")
    v = value.strip()
    if p["type"] == "int":
        if not re.fullmatch(r"\d{1,12}", v):
            raise ValueError("нужно целое число")
        n = int(v)
        if not (p["min"] <= n <= p["max"]):
            raise ValueError(f"диапазон {p['min']}..{p['max']}")
        return str(n)
    if p["type"] == "enum":
        if v not in p["values"]:
            raise ValueError("допустимо: " + ", ".join(p["values"]))
        return v
    if not re.fullmatch(p["re"], v):
        raise ValueError("недопустимое значение")
    if key == "mynetworks":
        _check_nets(v)
    return v
