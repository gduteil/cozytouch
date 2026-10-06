# Atlantic Cozytouch

The domain language of this integration: what the Cozytouch API's numbers are
called once they mean something. Glossary only — how things work is
`docs/architecture.md`, why a setting holds is `docs/decisions.md`.

## Language

### Devices and identity

**Gateway**:
The device the account's other devices hang off, named by them in
`masterDeviceId`. The API reports the link; Home Assistant only draws it when
the gateway was set up as a device of its own.
_Avoid_: hub (that word is taken — see Hub), bridge

**Hub**:
The per-device coordinator class in `hub.py`, one per subentry. Not the
gateway hardware, despite Atlantic selling a box called "HUB".
_Avoid_: using it for the gateway device

**Subentry**:
One device's registration under the account's config entry. Its id is the
device's identity in Home Assistant and the prefix of every unique id built
from it.

### Connectivity

**Cloud session**:
Whether the integration currently holds a working authenticated session to
Atlantic's cloud and its last setup-view read succeeded (`online`). A property
of the account, so the same answer on every device; when false, every device's
data is stale. A 429 backoff deliberately leaves it true — the poll is skipped,
last values stand. Surfaced as the CloudConnectivity binary sensor.
_Avoid_: online (the field name — the concept is the session); confusing it
with device availability.

**Device availability**:
The cloud's own flag for whether one device is reachable and reporting
(`isAvailable`), read per device from the setup view. Distinct from the cloud
session: the session can be working while a single device is unavailable. Read
raw — the cloud already reflects a child dropping off its gateway — and kept as
its own sensor rather than folded into the session one, so "the cloud is down"
and "this device is down" stay tellable apart. Only meaningful while the
session is working; otherwise stale like everything else.
_Avoid_: online (that is the session); connected (device-class wording, not the
concept).

### Capabilities

**Capability**:
One numbered value a device reports (`capabilityId` + string value). The
numeric id is the domain; what it becomes is the mapping's answer.

**Mapped / unmapped capability**:
Mapped means the table names it — nothing more. A capability can be mapped
and still build no entity; unmapped means nobody knows what it is yet, which
is what a diagnostics dump is read for.

**Self-describing capability**:
A capability whose encoding is unverified: named, surfaced as a raw string,
disabled by default, so it costs nobody anything until someone investigates.

### Weekly programs

**Program block**:
Seven consecutive capabilities holding a weekly program, Monday first — one
capability per day, each a matrix of slots. Named by its first id: 196
(heating / Z1), 203 (cooling / Z2), 237 (hot water), 100320 and 100327
(reduced milestones), 245 (time ranges).

**Slot**:
One `[minutes-past-midnight, setpoint]` row of a day's program. A slot runs
until the next one takes over; the last of the day holds until midnight.

**Covered block**:
A program block a calendar entity exists for — which requires the device to
report the block in full. The calendar is the canonical view of a covered
block; the per-day sensors of one are default-disabled duplicates (#42).

**Per-day program sensor**:
The raw text sensor of one day of one block (`prog_heating_monday`, …). Kept
for whoever re-enables it, never the primary view of a covered block.
_Avoid_: prog sensor (ambiguous with the week view), week sensor (a dropped
design — see issue #42)
