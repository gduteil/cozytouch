r"""Ask the Overkiz enduser plane whether it knows our magellan devices.

`docs/api-surface.md` rules out ~90 paths -- all of them on
apis.groupe-atlantic.com/magellan. The Overkiz plane was never probed, and
pyoverkiz reaches "Atlantic Cozytouch" there with the *same* credential we
already hold. Its login (pyoverkiz/auth/strategies.py, CozytouchAuthStrategy)
is our own token call, plus one GET on a magellan route we never tried:

    POST apis.groupe-atlantic.com/token               <- identical to ours
    GET  apis.groupe-atlantic.com/magellan/accounts/jwt
    POST ha110-1.overkiz.com/.../enduserAPI/login     (form field: jwt)

If the setup that comes back lists our ROOM_n units with a `widget` and a
`controllableName`, the vendor describes them somewhere after all, and
model.py could become an override layer instead of the source of truth.

Read-only: it logs in, GETs, prints shapes and counts. Device addresses are
redacted; what it prints is the identity vocabulary, which is the whole
question. Run from the repository root:

    umask 077
    pbpaste > ~/.cozytouch-pass          # keeps the password out of history
    COZYTOUCH_USER=you@example.com \
      COZYTOUCH_PASS_FILE=~/.cozytouch-pass \
      python3 scripts/probes/probe_overkiz_plane.py
    rm -f ~/.cozytouch-pass

A refused login stops the script rather than retrying: that is the one thing
that could lock the account, and why only the maintainer runs it (MEMORY.md).
Run on 2026-09-12: the jwt is minted, every enduserAPI/login answers 401
(`docs/api-surface.md`).
"""

import http.cookiejar
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

# Every Overkiz host the app binary names, in the order to try them. pyoverkiz
# knows only ha110-1 and points Atlantic, Sauter and Thermor at it; the other
# two come out of `strings` on the Cozytouch executable and are not in any
# client library, so a 401 on ha110-1 alone proves nothing about the account.
OVERKIZ_HOSTS = (
    "https://ha110-1.overkiz.com",
    "https://ha111-1.overkiz.com",
    "https://std14-1.overkiz.com",
)
ENDUSER_PATH = "/enduser-mobile-web/enduserAPI"

# What an Overkiz device declares about itself. The point of the probe: if
# these come back populated, the identity we reverse-engineer is published.
IDENTITY_FIELDS = ("controllableName", "widget", "uiClass", "type", "available")

REDACTED = "**REDACTED**"


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _atlantic import (  # noqa: E402 -- the path above is what makes it importable
    COZYTOUCH_ATLANTIC_API as API,
    COZYTOUCH_CLIENT_ID as CLIENT_ID,
)

opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
)


def _post(url, fields, headers):
    body = urllib.parse.urlencode(fields).encode()
    request = urllib.request.Request(url, data=body, headers=headers)
    with opener.open(request, timeout=30) as response:
        return response.status, response.read().decode()


def _get(url, headers):
    request = urllib.request.Request(url, headers=headers)
    with opener.open(request, timeout=30) as response:
        return response.status, response.read().decode()


def _password():
    path = os.environ.get("COZYTOUCH_PASS_FILE")
    if not path:
        sys.exit("Set COZYTOUCH_PASS_FILE (and COZYTOUCH_USER). See the docstring.")
    return pathlib.Path(path).expanduser().read_text().strip()


def main():
    user = os.environ.get("COZYTOUCH_USER")
    if not user:
        sys.exit("Set COZYTOUCH_USER. See the docstring.")

    print("1. token on our own host")
    try:
        _, raw = _post(
            # The integration's own route and fields, not pyoverkiz's: it posts
            # to /token without a scope, and this host answers that with a 400
            # that is not a credential rejection. Matching account.py exactly is
            # what keeps a malformed request from reading as a refused password.
            f"{API}/users/token",
            {
                "grant_type": "password",
                "scope": "openid",
                "username": f"GA-PRIVATEPERSON/{user}",
                "password": _password(),
            },
            {
                "Authorization": f"Basic {CLIENT_ID}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
    except urllib.error.HTTPError as err:
        # The body separates the two cases that must never be confused: an
        # `invalid_grant` is the password and must not be retried, anything
        # else is this script being wrong about the request.
        body = err.read().decode(errors="replace")[:300]
        sys.exit(f"   HTTP {err.code} -- stopping, not retrying.\n   body: {body}")

    token = json.loads(raw)
    if "access_token" not in token:
        sys.exit(f"   no access_token: {token.get('error_description', raw[:200])}")
    print("   ok")

    print("2. GET /magellan/accounts/jwt   (never tried before)")
    try:
        _, jwt = _get(
            f"{API}/magellan/accounts/jwt",
            {"Authorization": f"Bearer {token['access_token']}"},
        )
    except urllib.error.HTTPError as err:
        sys.exit(f"   {err.code} {err.reason} -- the plane is not reachable this way.")
    jwt = jwt.strip().strip('"')
    print(f"   ok, {len(jwt)} chars, {jwt.count('.') + 1} segments")

    endpoint = None
    for host in OVERKIZ_HOSTS:
        candidate = host + ENDUSER_PATH
        print(f"3. POST enduserAPI/login on {host.split('//')[1]}")
        try:
            _post(
                f"{candidate}/login",
                {"jwt": jwt},
                {"Content-Type": "application/x-www-form-urlencoded"},
            )
        except urllib.error.HTTPError as err:
            # No password is spent here -- the jwt is already minted -- so an
            # unsuccessful host is worth stepping past rather than stopping on.
            print(f"   {err.code} {err.reason}")
            continue
        print("   ok, session established")
        endpoint = candidate
        break

    if endpoint is None:
        sys.exit("   no session on any Overkiz host the app names.")

    print("4. GET enduserAPI/setup")
    try:
        _, raw = _get(f"{endpoint}/setup", {"Accept": "application/json"})
    except urllib.error.HTTPError as err:
        sys.exit(f"   {err.code} {err.reason}")

    setup = json.loads(raw)
    devices = setup.get("devices", [])
    print(f"   {len(devices)} device(s)\n")

    for device in devices:
        url = device.get("deviceURL", "")
        # The address names a household; the protocol prefix does not.
        protocol = url.split("://")[0] if "://" in url else url
        print(f"--- {protocol}://{REDACTED}")
        for field in IDENTITY_FIELDS:
            print(f"    {field}: {device.get(field)}")
        definition = device.get("definition") or {}
        states = [s.get("qualifiedName") for s in definition.get("states", [])]
        commands = [c.get("commandName") for c in definition.get("commands", [])]
        print(f"    definition: {len(states)} states, {len(commands)} commands")
        print(f"    states: {states[:12]}")
        print(f"    commands: {commands[:12]}")
        print()


if __name__ == "__main__":
    main()
