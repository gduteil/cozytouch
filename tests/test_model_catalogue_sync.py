"""The two model tables against the catalogue the watcher keeps.

`model_catalogue.py` and `model_product_ids.py` were generated from the
vendor's model catalogue, and `scripts/model_catalogue.jsonl` is that
catalogue as last read. When the watcher's issue lands and somebody commits a
new read, this is what says which table is now behind -- rather than the
tables drifting quietly from the file next to them.

A model the catalogue drops stays in both tables, listed in
`DROPPED_FROM_CATALOGUE` : the tables answer for every model the catalogue has
ever listed, and the file only for what it lists now.
"""

import json
import pathlib
import re

from custom_components.cozytouch.model_catalogue import (
    DROPPED_FROM_CATALOGUE,
    MODEL_CATALOGUE,
)
from custom_components.cozytouch.model_product_ids import (
    LEARNED_FROM_DUMPS,
    PRODUCT_IDS,
)

CATALOGUE = (
    pathlib.Path(__file__).resolve().parent.parent
    / "scripts"
    / "model_catalogue.jsonl"
)
ROWS = [json.loads(line) for line in CATALOGUE.read_text().splitlines()]

# A firmware slot, not a product: `BD1 DEFAULT`, `ROOM_0`, `UI_3`.
SLOT = re.compile(r"(ROOM|UI)_\d+|.* default", re.IGNORECASE)


def test_every_product_in_the_catalogue_is_named_as_the_vendor_spells_it():
    expected = {
        row["id"]: " ".join(row["longName"].split())
        for row in ROWS
        if row["longName"] is not None and not SLOT.fullmatch(row["longName"])
    }
    listed = {
        modelId: name
        for modelId, name in MODEL_CATALOGUE.items()
        if modelId not in DROPPED_FROM_CATALOGUE
    }
    assert expected == listed


def test_every_product_id_is_the_catalogues_unless_a_dump_corrected_it():
    expected = {row["id"]: row["productId"] for row in ROWS if row["productId"]}
    listed = {
        modelId: productId
        for modelId, productId in PRODUCT_IDS.items()
        if modelId not in DROPPED_FROM_CATALOGUE
    }
    assert expected | LEARNED_FROM_DUMPS == listed


def test_a_dropped_model_is_one_the_catalogue_no_longer_lists():
    assert DROPPED_FROM_CATALOGUE.isdisjoint(row["id"] for row in ROWS)


def test_a_dropped_model_keeps_its_name():
    assert DROPPED_FROM_CATALOGUE.issubset(MODEL_CATALOGUE)
