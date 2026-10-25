"""What a 1.4 install sees when its entries cannot be migrated.

The migration (tests/test_migrate_1_4.py) folds 1.4's entries into one
account entry, unless the account was added again by hand first. Those
entries get a sentence instead of a bare MIGRATION_ERROR : one notice in
Repairs however many are left, gone once the last is deleted.
"""

import asyncio
from types import SimpleNamespace

from test_faults import FakeRegistry

from custom_components.cozytouch import async_migrate_entry, async_remove_entry, repairs
from custom_components.cozytouch.repairs import LEGACY_ENTRY_ISSUE


def entry(entry_id, version=1):
    return SimpleNamespace(
        entry_id=entry_id,
        version=version,
        minor_version=1,
        title=entry_id,
        unique_id="cozytouch_fake@example.com" if version == 2 else None,
        data={"username": "fake@example.com", "deviceId": 1, "name": entry_id},
    )


def hass_with(*entries):
    return SimpleNamespace(
        config_entries=SimpleNamespace(async_entries=lambda domain: list(entries))
    )


def test_a_1_4_entry_the_account_already_replaced_raises_the_notice(monkeypatch):
    registry = FakeRegistry()
    monkeypatch.setattr(repairs, "ir", registry)
    old = entry("ROOM_0")
    hass = hass_with(old, entry("account", 2))
    hass.data = {}

    assert asyncio.run(async_migrate_entry(hass, old)) is False
    assert [issue for issue, _ in registry.created] == [LEGACY_ENTRY_ISSUE]


def test_the_notice_stays_while_another_1_4_entry_is_left(monkeypatch):
    registry = FakeRegistry()
    monkeypatch.setattr(repairs, "ir", registry)
    first, second = entry("ROOM_0"), entry("ROOM_1")

    asyncio.run(async_remove_entry(hass_with(first, second), first))

    assert registry.deleted == []


def test_deleting_the_last_1_4_entry_clears_the_notice(monkeypatch):
    registry = FakeRegistry()
    monkeypatch.setattr(repairs, "ir", registry)
    last = entry("ROOM_0")

    asyncio.run(async_remove_entry(hass_with(last, entry("account", 2)), last))

    assert registry.deleted == [LEGACY_ENTRY_ISSUE]
