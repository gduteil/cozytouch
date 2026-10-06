"""The login the scripts share, with nothing but the standard library.

The catalogue watcher runs on a bare runner with no aiohttp and no Home
Assistant, so neither is imported here, directly or through the package.
What a refused login then means is each caller's to decide.
"""

import importlib.util
import json
import os
import pathlib
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _const():
    """`const.py` alone, loaded by path rather than as part of the package.

    Importing `custom_components.cozytouch.const` runs the package's
    `__init__`, which pulls in aiohttp and Home Assistant. `const.py` itself
    imports only `enum`.
    """
    spec = importlib.util.spec_from_file_location(
        "cozytouch_const", ROOT / "custom_components" / "cozytouch" / "const.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CONST = _const()
COZYTOUCH_ATLANTIC_API = _CONST.COZYTOUCH_ATLANTIC_API
COZYTOUCH_CLIENT_ID = _CONST.COZYTOUCH_CLIENT_ID


def password() -> str | None:
    """COZYTOUCH_PASS_FILE, else COZYTOUCH_PASS, else None.

    Only the line ending is stripped from the file: it comes from an editor or
    a shell redirect, while a space may be part of the password.
    """
    path = os.environ.get("COZYTOUCH_PASS_FILE")
    if path:
        return pathlib.Path(path).expanduser().read_text().strip("\r\n")
    return os.environ.get("COZYTOUCH_PASS")


def token(secret: str, timeout: int) -> str:
    """One login; an HTTPError is left to the caller."""
    data = urllib.parse.urlencode(
        {
            "grant_type": "password",
            "scope": "openid",
            "username": "GA-PRIVATEPERSON/" + os.environ["COZYTOUCH_USER"],
            "password": secret,
        }
    ).encode()
    req = urllib.request.Request(
        COZYTOUCH_ATLANTIC_API + "/users/token",
        data=data,
        headers={
            "Authorization": f"Basic {COZYTOUCH_CLIENT_ID}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode())["access_token"]
