"""Which products are offered the identify control, and which only read it.

Capability 100078 makes a device announce itself so somebody standing in the
room can tell which of three identical boxes they are looking at. Whether it
is a control is not something the device reports : the vendor's
`GacomaDeviceFactory` picks a class from the pair (own `productId`,
parent's) and each class carries the answer as a constant. `winkable`
reproduces that, and these pin the pairs it turns on. See docs/decisions.md.
"""

import pytest

from custom_components.cozytouch.capability import get_capability_infos
from custom_components.cozytouch.model import PRODUCT_IDS, get_model_infos

IDENTIFY = 100078

# The vendor indexes products by `productId`, and the mapping keys on model
# ids, so each case names the product it means and looks one up.
FIRST_MODEL_OF = {}
for _modelId, _productId in sorted(PRODUCT_IDS.items()):
    FIRST_MODEL_OF.setdefault(_productId, _modelId)

BD0 = 41
TD1 = 53
AIR_CONDITIONER_UI = 31
TH_ZONE = 65
ROOM = 26
AIR_CONDITIONER = 25
NAVI_HUB = 63


def identify(productId, parentProductId=None):
    infos = get_model_infos(
        FIRST_MODEL_OF[productId],
        masterModelId=(
            FIRST_MODEL_OF[parentProductId] if parentProductId else None
        ),
    )
    return get_capability_infos(infos, IDENTIFY, "0", {IDENTIFY})["type"]


@pytest.mark.parametrize(
    "productId", [BD0, TD1, AIR_CONDITIONER_UI]
)
def test_the_products_whose_class_winks_get_a_control(productId):
    """GacomaBD0, GacomaTD1 and GacomaAirConditionerUI all say true, and none
    of them reads the parent to decide.
    """
    assert identify(productId) == "switch"
    assert identify(productId, NAVI_HUB) == "switch"


def test_a_zone_behind_a_hub_is_a_transverse_ui_and_winks():
    assert identify(TH_ZONE, NAVI_HUB) == "switch"


def test_a_zone_behind_nothing_does_not():
    """The factory builds no class for that pair, so there is no button."""
    assert identify(TH_ZONE) == "binary"


@pytest.mark.parametrize("parentProductId", [None, NAVI_HUB, AIR_CONDITIONER])
def test_a_room_only_reads_it(parentProductId):
    """Both classes a room resolves to say false -- GacomaAirConditionerRoom
    behind a bare air conditioner, and TransverseRoom behind a hub, which is
    not a settings device at all.
    """
    assert identify(ROOM, parentProductId) == "binary"


def test_a_hub_only_reads_it():
    assert identify(AIR_CONDITIONER) == "binary"


@pytest.mark.parametrize("productId", [BD0, ROOM])
def test_it_arrives_off_either_way(productId):
    """One device makes it pointless and dozens of descriptors make it noise."""
    infos = get_model_infos(FIRST_MODEL_OF[productId])
    result = get_capability_infos(infos, IDENTIFY, "0", {IDENTIFY})

    assert result["enabled_by_default"] is False
