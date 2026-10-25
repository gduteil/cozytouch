"""1.4's entries, one per device, folded into one account entry.

What has to hold is what keeps an entity's history : its registry entry is
moved, not recreated, so its entity id does not change. The unique id and
the device identifier change only by the prefix 1.4 built them from, the
entry id, which becomes the subentry id. Checked end to end on the test
Home Assistant (docs/decisions.md, *1.4 entries are migrated*) ; this pins
the bookkeeping through fakes at the registry seam, the way
tests/test_prog_visibility.py does.
"""

import asyncio
from types import SimpleNamespace

from custom_components.cozytouch import migrate_1_4


def v1(entry_id, deviceId, username="Me@Example.com"):
    return SimpleNamespace(
        entry_id=entry_id,
        version=1,
        minor_version=1,
        unique_id=f"cozytouch_{deviceId}",
        title=f"device {deviceId}",
        data={
            "username": username,
            "password": "secret",
            "deviceId": deviceId,
            "name": f"device {deviceId}",
            "create_unknown": True,
            "dump_json": False,
        },
        subentries={},
    )


class FakeEntries:
    def __init__(self, entries):
        self.entries = entries
        self.removed = []

    def async_entries(self, domain):
        return list(self.entries)

    def async_update_entry(self, entry, **changes):
        for key, value in changes.items():
            setattr(entry, key, value)

    def async_add_subentry(self, entry, subentry):
        entry.subentries = entry.subentries | {subentry.subentry_id: subentry}

    async def async_remove(self, entry_id):
        self.removed.append(entry_id)


class FakeEntityRegistry:
    def __init__(self, by_entry):
        self.by_entry = by_entry
        self.updates = {}

    def async_update_entity(self, entity_id, **changes):
        self.updates[entity_id] = changes


class FakeDeviceRegistry:
    def __init__(self, by_entry):
        self.by_entry = by_entry
        self.updates = []

    def async_update_device(self, device_id, **changes):
        self.updates.append((device_id, changes))


def run(monkeypatch, entries, entities, devices, which=0):
    hass = SimpleNamespace(
        data={},
        config_entries=FakeEntries(entries),
        async_create_task=lambda coro: asyncio.get_event_loop().create_task(coro),
        bus=SimpleNamespace(async_listen_once=lambda event, listener: None),
    )
    ereg, dreg = FakeEntityRegistry(entities), FakeDeviceRegistry(devices)
    monkeypatch.setattr(migrate_1_4.er, "async_get", lambda hass: ereg)
    monkeypatch.setattr(
        migrate_1_4.er,
        "async_entries_for_config_entry",
        lambda reg, entry_id: reg.by_entry.get(entry_id, []),
    )
    monkeypatch.setattr(migrate_1_4.dr, "async_get", lambda hass: dreg)
    monkeypatch.setattr(
        migrate_1_4.dr,
        "async_entries_for_config_entry",
        lambda reg, entry_id: reg.by_entry.get(entry_id, []),
    )

    async def go():
        result = await migrate_1_4.async_migrate_from_1_4(hass, entries[which])
        await asyncio.sleep(0)
        return result

    return asyncio.run(go()), hass, ereg, dreg


def entity(entity_id, unique_id):
    return SimpleNamespace(entity_id=entity_id, unique_id=unique_id)


def device(device_id, entry_id):
    return SimpleNamespace(id=device_id, identifiers={("cozytouch", entry_id)})


def test_the_first_entry_becomes_the_account_and_takes_the_others_in(monkeypatch):
    first, second = v1("E1", 101), v1("E2", 102)
    entities = {
        "E1": [entity("climate.salon", "cozytouch_E1_climate_7")],
        "E2": [entity("datetime.absence_debut", "E2_0")],
    }
    devices = {"E1": [device("D1", "E1")], "E2": [device("D2", "E2")]}

    result, hass, ereg, dreg = run(monkeypatch, [first, second], entities, devices)

    assert result is True
    assert (first.version, first.minor_version) == (2, 1)
    assert first.unique_id == "cozytouch_me@example.com"
    assert first.data == {"username": "Me@Example.com", "password": "secret"}
    assert first.options == {"create_unknown": True, "dump_json": False}

    by_device = {s.data["deviceId"]: s for s in first.subentries.values()}
    assert sorted(by_device) == [101, 102]
    sub1, sub2 = by_device[101].subentry_id, by_device[102].subentry_id
    assert by_device[102].unique_id == "cozytouch_102"

    assert ereg.updates == {
        "climate.salon": {
            "config_entry_id": "E1",
            "config_subentry_id": sub1,
            "new_unique_id": f"cozytouch_{sub1}_climate_7",
        },
        "datetime.absence_debut": {
            "config_entry_id": "E1",
            "config_subentry_id": sub2,
            "new_unique_id": f"{sub2}_0",
        },
    }
    assert dreg.updates[2] == (
        "D2",
        {
            "add_config_entry_id": "E1",
            "add_config_subentry_id": sub2,
            "new_identifiers": {("cozytouch", sub2)},
        },
    )
    assert dreg.updates[3] == (
        "D2",
        {"remove_config_entry_id": "E2", "remove_config_subentry_id": None},
    )
    assert hass.config_entries.removed == ["E2"]


def test_an_entry_already_taken_in_answers_none(monkeypatch):
    first, second = v1("E1", 101), v1("E2", 102)
    _, hass, _, _ = run(monkeypatch, [first, second], {}, {})

    result = asyncio.run(migrate_1_4.async_migrate_from_1_4(hass, second))

    assert result is None


def test_two_accounts_stay_two_entries(monkeypatch):
    mine, theirs = v1("E1", 101), v1("E2", 102, username="other@example.com")

    _, hass, _, _ = run(monkeypatch, [mine, theirs], {}, {})

    assert [s.data["deviceId"] for s in mine.subentries.values()] == [101]
    assert hass.config_entries.removed == []
    assert theirs.version == 1


def test_an_account_added_again_by_hand_is_not_merged_into(monkeypatch):
    old = v1("E1", 101)
    account = SimpleNamespace(
        entry_id="A", version=2, unique_id="cozytouch_me@example.com"
    )

    result, _, ereg, _ = run(monkeypatch, [old, account], {}, {})

    assert result is False
    assert old.version == 1
    assert ereg.updates == {}
