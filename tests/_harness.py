"""What several test files build the same way: one platform over one hub."""

import asyncio
import pathlib
from types import SimpleNamespace

SUBENTRY_ID = "sub-1"

# strings.json first: it is the reference the others are compared against.
# The rest is a glob, so a language contributed later is held to the same
# completeness without anyone editing this line.
TRANSLATIONS = (
    "custom_components/cozytouch/strings.json",
    *sorted(
        str(path)
        for path in pathlib.Path("custom_components/cozytouch/translations").glob(
            "*.json"
        )
    ),
)


def entry_over(hub, deviceId=27906641):
    """An account entry holding one device, which is what a subentry is."""
    return SimpleNamespace(
        runtime_data=SimpleNamespace(
            hubs={SUBENTRY_ID: hub},
            # An account whose setup reports no consumption, which is most of
            # them ; tests/test_consumption.py covers the ones that do.
            account=SimpleNamespace(consumptions=None, setup={}),
            coordinator=None,
        ),
        subentries={
            SUBENTRY_ID: SimpleNamespace(data={"deviceId": deviceId}, title="Salon")
        },
        title="cozytouch@example.com",
        entry_id="entry123",
    )


def set_up(platform, entry):
    """Run a platform's async_setup_entry and return the entities it added."""
    entities = []
    asyncio.run(
        platform.async_setup_entry(
            None,
            entry,
            lambda new, update_before_add, config_subentry_id=None: entities.extend(
                new
            ),
        )
    )
    return entities
