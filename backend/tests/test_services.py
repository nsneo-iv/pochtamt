"""Проверки сервисов, не требующие внешних систем."""
from app.config import settings
from app.security import hash_password, verify_password
from app.services import ad, dkim


def test_password_hash_dovecot_format():
    h = hash_password("secret-pass")
    assert h.startswith("{BLF-CRYPT}$2b$12$")
    assert verify_password("secret-pass", h)
    assert not verify_password("wrong", h)


def test_dkim_generate_and_record():
    priv, pub = dkim.generate()
    assert priv.startswith("-----BEGIN ") and "PRIVATE KEY" in priv
    name, value = dkim.dns_record("example.com", "mail", pub)
    assert name == "mail._domainkey.example.com"
    assert value.startswith("v=DKIM1; k=rsa; p=MII")


def test_normalize_login_with_ad(monkeypatch):
    monkeypatch.setattr(settings, "ad_ldap_uri", "ldaps://dc.corp.local:3269")
    monkeypatch.setattr(settings, "ad_upn_suffix", "corp.local")
    monkeypatch.setattr(settings, "ad_netbios", "CORP")
    assert ad.enabled()
    assert ad.normalize_login("User") == "user@corp.local"
    assert ad.normalize_login("CORP\\User") == "user@corp.local"
    assert ad.normalize_login("user@corp.local") == "user@corp.local"
    assert ad.normalize_login("CHILD-DC\\u") == "u@child-dc"


def test_normalize_login_without_ad(monkeypatch):
    monkeypatch.setattr(settings, "ad_ldap_uri", "")
    assert not ad.enabled()
    assert ad.normalize_login("  Admin ") == "admin"
    assert ad.normalize_login("CORP\\User") == "corp\\user"
    assert ad.authenticate("admin", "x") is None
