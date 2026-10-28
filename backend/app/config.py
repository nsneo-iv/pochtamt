"""Настройки бэкенда. Читаются из backend/.env (переменные окружения имеют приоритет)."""
import os

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    def require_secrets(self) -> None:
        """Вызывается при старте API и cli (не при импорте: тесты и CI импортируют модули без .env).
        Слабый ключ подписи = любой может выписать себе токен админа."""
        if self.jwt_secret in ("", "changeme") or len(self.jwt_secret) < 32:
            raise SystemExit("JWT_SECRET: задайте случайную строку не короче 32 символов (openssl rand -hex 32)")

    # PostgreSQL под ролью mail_app
    db_dsn: str = "postgresql://mail_app:changeme@127.0.0.1:5432/mail"

    # JWT для сессий панели
    jwt_secret: str = "changeme"
    jwt_ttl_minutes: int = 120

    # Active Directory (необязательно): вход админов и ящиков auth=ad, синхронизация. Пустой AD_LDAP_URI —
    # AD выключен: админы входят по локальному паролю (admin-add --password), ящики только auth=local
    ad_ldap_uri: str = ""
    ad_bind_user: str = ""
    ad_bind_password: str = ""
    ad_base_dn: str = ""
    ad_upn_suffix: str = ""                     # короткий логин «user» превращается в user@<суффикс>
    ad_netbios: str = ""                        # логин «NETBIOS\user» тоже принимается
    ad_tls_verify: bool = True                  # проверять сертификат DC (для самоподписанного — CA в системе)

    @property
    def ad_enabled(self) -> bool:
        return bool(self.ad_ldap_uri)

    # имя почтового хоста: с ним сравнивается MX в проверке DNS на дашборде домена
    mail_hostname: str = "mail.example.com"

    # контроллер Rspamd: статистика антиспама/антивируса для сводки (пароль — RSPAMD_PASSWORD из install/.env)
    rspamd_url: str = "http://127.0.0.1:11334"
    rspamd_password: str = ""

    # Redis (ключи DKIM для Rspamd)
    redis_url: str = "redis://:changeme@127.0.0.1:6379/0"

    # ManageSieve: master-пользователь Dovecot для заливки Sieve-скриптов (логин «ящик*panel»)
    sieve_host: str = "mail.example.com"
    sieve_port: int = 4190
    sieve_master_user: str = "panel"
    sieve_master_password: str = ""

    # агент на почтовом хосте (очередь Postfix, квоты Dovecot)
    agent_url: str = "http://127.0.0.1:8025"
    agent_token: str = ""

    # запуск
    listen_host: str = "127.0.0.1"
    listen_port: int = 8000
    cors_origins: list[str] = []


settings = Settings()
