"""Which `productId` each model id carries, from the vendor's own catalogue.

The setup view sends a device's `productId` with the device, and that is what
`model.py` classifies on. This table answers the same question for a model id
with no device beside it -- a diagnostics dump, a repair, a test -- and for a
device whose payload leaves the field out.

Generated from the vendor's model catalogue (`scripts/model_catalogue.jsonl`,
`GET /magellan/productmodels/models`), as contiguous runs : 1231 ids, 104
distinct product ids, 168 runs. Ids the vendor assigns no product id are
absent rather than carried as 0. Regenerate, never edit by hand.
"""

# (first model id, last model id, productId)
PRODUCT_ID_RUNS: tuple[tuple[int, int, int], ...] = (
    (1, 12, 1),
    (25, 25, 2),
    (29, 29, 2),
    (32, 32, 2),
    (34, 39, 2),
    (54, 69, 1),
    (73, 86, 2),
    (87, 87, 3),
    (91, 95, 2),
    (215, 220, 2),
    (232, 232, 1),
    (233, 233, 2),
    (234, 234, 3),
    (235, 235, 4),
    (236, 236, 7),
    (237, 237, 8),
    (238, 238, 9),
    (239, 239, 10),
    (240, 240, 11),
    (241, 241, 12),
    (242, 242, 13),
    (243, 243, 14),
    (244, 244, 15),
    (245, 245, 16),
    (246, 246, 17),
    (247, 247, 18),
    (248, 248, 19),
    (249, 249, 20),
    (250, 250, 21),
    (251, 251, 22),
    (252, 252, 23),
    (253, 261, 1),
    (265, 267, 1),
    (269, 270, 1),
    (272, 324, 1),
    (325, 332, 2),
    (333, 353, 1),
    (354, 367, 2),
    (368, 373, 3),
    (374, 375, 2),
    (376, 378, 3),
    (379, 385, 24),
    (386, 394, 7),
    (395, 415, 1),
    (426, 437, 2),
    (441, 444, 2),
    (446, 446, 2),
    (447, 454, 1),
    (457, 516, 1),
    (517, 552, 24),
    (553, 555, 2),
    (556, 556, 25),
    (557, 557, 26),
    (558, 558, 27),
    (559, 559, 28),
    (560, 560, 29),
    (561, 561, 30),
    (562, 562, 31),
    (563, 563, 32),
    (564, 564, 33),
    (565, 565, 34),
    (566, 566, 35),
    (567, 567, 36),
    (568, 568, 37),
    (569, 569, 38),
    (570, 570, 39),
    (571, 571, 40),
    (572, 572, 41),
    (573, 573, 42),
    (574, 574, 43),
    (1353, 1353, 44),
    (1361, 1363, 4),
    (1364, 1366, 7),
    (1367, 1376, 47),
    (1377, 1377, 51),
    (1378, 1378, 50),
    (1379, 1379, 52),
    (1380, 1386, 53),
    (1387, 1387, 54),
    (1388, 1388, 55),
    (1389, 1389, 56),
    (1390, 1390, 57),
    (1391, 1391, 58),
    (1432, 1434, 58),
    (1461, 1504, 64),
    (1505, 1505, 65),
    (1506, 1506, 66),
    (1507, 1507, 67),
    (1508, 1508, 68),
    (1509, 1509, 69),
    (1510, 1510, 70),
    (1511, 1511, 71),
    (1512, 1512, 72),
    (1513, 1513, 73),
    (1514, 1514, 74),
    (1515, 1515, 75),
    (1516, 1516, 76),
    (1517, 1517, 77),
    (1518, 1518, 78),
    (1519, 1519, 79),
    (1520, 1520, 80),
    (1521, 1521, 81),
    (1522, 1522, 82),
    (1523, 1523, 83),
    (1524, 1524, 84),
    (1525, 1525, 85),
    (1526, 1526, 86),
    (1527, 1527, 87),
    (1528, 1528, 88),
    (1529, 1529, 89),
    (1530, 1530, 90),
    (1531, 1531, 91),
    (1532, 1532, 92),
    (1533, 1533, 93),
    (1534, 1534, 94),
    (1535, 1539, 62),
    (1540, 1640, 53),
    (1641, 1679, 62),
    (1680, 1680, 95),
    (1681, 1681, 96),
    (1685, 1704, 54),
    (1705, 1705, 58),
    (1707, 1710, 54),
    (1713, 1728, 54),
    (1730, 1733, 54),
    (1734, 1734, 97),
    (1735, 1735, 98),
    (1736, 1736, 99),
    (1737, 1737, 100),
    (1738, 1738, 101),
    (1739, 1739, 102),
    (1740, 1740, 103),
    (1741, 1741, 104),
    (1742, 1742, 105),
    (1743, 1743, 106),
    (1744, 1744, 107),
    (1745, 1745, 108),
    (1746, 1746, 109),
    (1747, 1747, 110),
    (1748, 1748, 111),
    (1749, 1752, 62),
    (1753, 1753, 112),
    (1754, 1757, 47),
    (1758, 1758, 96),
    (1759, 1762, 47),
    (1763, 1763, 6),
    (1764, 1815, 64),
    (1816, 1939, 53),
    (1940, 1947, 54),
    (1948, 2007, 47),
    (2128, 2131, 53),
    (2132, 2134, 54),
    (2135, 2138, 58),
    (2145, 2145, 54),
    (2146, 2146, 58),
    (2147, 2294, 53),
    (2295, 2325, 54),
    (2326, 2330, 58),
    (2341, 2341, 3),
    (2342, 2342, 54),
    (2343, 2343, 58),
    (2344, 2344, 6),
    (2345, 2352, 47),
    (2353, 2353, 113),
    (2354, 2362, 54),
    (2363, 2371, 58),
    (2372, 2388, 62),
    (2415, 2440, 53),
)

# What a live payload sent where the catalogue's column is empty. Atlantic
# fills `productId` on the wire for models its own catalogue leaves at 0, and
# its app reads nothing else, so a diagnostics dump can correct a row here.
# 1457 came from one : the catalogue says 0, the account says 63.
#
# The CozyBox sends 63, the same as the HUB Cozytouch, and the same
# `Connectivity_Box` family, while one drives radiators and the other air
# conditioners. That used to make it unusable here -- taking it would have
# turned issue #172's radiators into air conditioners. It no longer decides
# anything about the rooms behind it, so it can be read like any other.
# 2448-2450 are the same box under three more badges.
#
# 1447 is left out : it sends 4, which the vendor calls DARWIN_BOILER and
# builds a thermostat widget for, where this table has the Naema 3 as a gas
# boiler. Claiming it would retype the appliance on the strength of a widget
# name. See docs/decisions.md.
LEARNED_FROM_DUMPS: dict[int, int] = {
    1457: 63,
    2447: 63,
    2448: 63,  # badge only
    2449: 63,  # badge only
    2450: 63,  # badge only
}

PRODUCT_IDS: dict[int, int] = {
    modelId: productId
    for first, last, productId in PRODUCT_ID_RUNS
    for modelId in range(first, last + 1)
} | LEARNED_FROM_DUMPS
