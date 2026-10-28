"""Проверки валидации адресов и схем (без базы)."""
import pytest

from app.models import AliasIn, MailboxIn, norm_address, norm_domain


def test_norm_domain():
    assert norm_domain(" Example.COM. ") == "example.com"
    with pytest.raises(ValueError):
        norm_domain("localhost")
    with pytest.raises(ValueError):
        norm_domain("-bad.ru")


def test_norm_address():
    assert norm_address("User.Name+tag@Example.com") == "user.name+tag@example.com"
    assert norm_address("@example.com", allow_catchall=True) == "@example.com"
    with pytest.raises(ValueError):
        norm_address("@example.com")
    with pytest.raises(ValueError):
        norm_address("no-at-sign")
    with pytest.raises(ValueError):
        norm_address("sp ace@example.com")


def test_alias_targets_dedup_sorted():
    a = AliasIn(address="Info@example.com", targets=["b@example.com", "A@example.com", "b@example.com"])
    assert a.address == "info@example.com"
    assert a.targets == ["a@example.com", "b@example.com"]


def test_mailbox_defaults():
    m = MailboxIn(address="u@example.com", password="12345678")
    assert m.auth == "local" and m.quota_mb == 1024 and m.ad_upn is None
    with pytest.raises(ValueError):
        MailboxIn(address="u@example.com", password="short")
