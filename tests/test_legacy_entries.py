"""What a 1.4 install sees after updating.

1.4 made one entry per device ; this version makes one per account and does
not migrate them (docs/decisions.md, *1.4 entries are not migrated*). What it
owes those users is a sentence instead of a bare MIGRATION_ERROR : one notice
in Repairs however many old entries there are, gone once the last is deleted.
"""

import asyncio
from types import SimpleNamespace

from test_faults import FakeRegistry

from custom_components.cozytouch import async_migrate_entry, async_remove_entry, repairs
from custom_components.cozytouch.repairs import LEGACY_ENTRY_ISSUE


def entry(entry_id, version=1):
    return SimpleNamespace(
        entry_id=entry_id, version=version, minor_version=1, title=entry_id
    )


def hass_with(*entries):
    return SimpleNamespace(
        config_entries=SimpleNamespace(async_entries=lambda domain: list(entries))
    )


def test_a_1_4_entry_fails_its_migration_and_raises_the_notice(monkeypatch):
    registry = FakeRegistry()
    monkeypatch.setattr(repairs, "ir", registry)

    assert asyncio.run(async_migrate_entry(None, entry("ROOM_0"))) is False
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
