r"""Re-read Atlantic's catalogues and say what moved since last time.

`GET /magellan/productmodels/capabilities` is the vendor's own list : every
capability id with its name, description, type, unit, bounds, enum members and
an accessType bitmask. `capability_table.py` was built from a run of it, and
nothing tells us when Atlantic edits it -- a new id, a renamed one, an enum
that gained a value. A device reporting an unmapped id eventually says so
through the diagnostics dump, but only once somebody owns that hardware.

`GET /magellan/productmodels/models` is the same for model ids : the name
and `productId` that `model_catalogue.py` and `model_product_ids.py` were
generated from. A model added there is hardware that will arrive unnamed.
`GET /magellan/productmodels/products` lists the `productId`s themselves, and
one added there is a kind of device `model.py` has never classified.

So each answer is kept in the repository, one item per line, and this
re-fetches all three with one token and leaves the files rewritten. `git diff` is
the report. Run from the repository root :

    umask 077
    pbpaste > ~/.cozytouch-pass
    COZYTOUCH_USER=you@example.com \
      COZYTOUCH_PASS_FILE=~/.cozytouch-pass \
      python3 scripts/check_capability_catalogue.py
    rm -f ~/.cozytouch-pass

Exit code 0 when nothing moved, CHANGED when a file changed, UNREACHABLE
when the fetch itself failed -- which is what `.github/workflows/catalogue.yaml`
branches on. Neither is 1: Python exits 1 on an uncaught traceback, so a
crashed run would otherwise read as "Atlantic changed the catalogue" and open
an issue whose diff is empty. That is exactly what happened on the first run,
issue #144.

One login, no retry. A refused login is reported and the run stops : repeated
failed logins are what could lock the account, and a fortnightly job that
retries is exactly how that would happen unattended.
"""

import json
import pathlib
import sys
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _atlantic
from _atlantic import (
    COZYTOUCH_ATLANTIC_API,
    COZYTOUCH_CLIENT_ID,  # noqa: F401 -- test_catalogue_watch reads it here
)

ROOT = _atlantic.ROOT
# route under /magellan/productmodels : (file, the fewest items an answer
# that was not truncated holds -- 405, 2299 and 123 when each was first read)
CATALOGUES = {
    "capabilities": (ROOT / "scripts" / "capability_catalogue.jsonl", 300),
    "models": (ROOT / "scripts" / "model_catalogue.jsonl", 2000),
    "products": (ROOT / "scripts" / "product_catalogue.jsonl", 100),
}

CHANGED = 10
UNREACHABLE = 2


def token() -> str:
    """One login with the password, or exit when none is set."""
    secret = _atlantic.password()
    if secret is None:
        sys.exit("Set COZYTOUCH_PASS_FILE (preferred) or COZYTOUCH_PASS.")
    return _atlantic.token(secret, timeout=30)


def catalogue(access_token: str, route: str) -> list[dict]:
    req = urllib.request.Request(
        COZYTOUCH_ATLANTIC_API + "/magellan/productmodels/" + route,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode())


def rendered(items: list[dict]) -> str:
    """One item per line, sorted, so a diff points at what changed.

    Sorted by id and with sorted keys, because the API's own ordering is not
    promised and a reshuffle would read as every item changing.
    """
    lines = [
        json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        for item in sorted(items, key=lambda item: item["id"])
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    try:
        access_token = token()
        answers = {route: catalogue(access_token, route) for route in CATALOGUES}
    except urllib.error.HTTPError as err:
        print(f"{err.code} from Atlantic: {err.read().decode()[:200]}", file=sys.stderr)
        return UNREACHABLE
    except OSError as err:
        print(f"could not reach Atlantic: {err}", file=sys.stderr)
        return UNREACHABLE

    # A truncated answer would otherwise land as "Atlantic deleted 300
    # capabilities", which is the one diff nobody should ever be shown. All
    # are checked before any is written, so a run is all or nothing.
    for route, items in answers.items():
        if len(items) < CATALOGUES[route][1]:
            print(
                f"only {len(items)} {route} came back; refusing to write.",
                file=sys.stderr,
            )
            return UNREACHABLE

    status = 0
    for route, items in answers.items():
        path = CATALOGUES[route][0]
        new = rendered(items)
        old = path.read_text() if path.exists() else ""
        if new == old:
            print(f"{len(items)} {route}, unchanged.")
            continue

        path.write_text(new)
        print(f"{len(items)} {route}, and the catalogue changed.")
        status = CHANGED
    return status


if __name__ == "__main__":
    sys.exit(main())
