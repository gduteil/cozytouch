"""A throwaway Home Assistant running this integration against a fake cloud.

`fake_atlantic.py` serves a diagnostics dump as if it were the account ; this
starts it, starts Home Assistant with the integration copied from the working
tree -- its API address pointed at the fake -- onboards an owner and adds the
account, so the result is a running instance with every device of the dump
on it. Nobody's credentials are involved. `.claude/skills/verify-cozytouch`
is the walk-through.

    python scripts/test_ha/run.py setup            # once : the HA venv
    python scripts/test_ha/run.py start [DUMP]     # fresh instance
    python scripts/test_ha/run.py restart          # recopy the code, restart
    python scripts/test_ha/run.py stop
    python scripts/test_ha/run.py states [TEXT]    # entities, filtered
    python scripts/test_ha/run.py call DOMAIN.SERVICE [JSON]
    python scripts/test_ha/run.py device ENTITY_ID # its device page path
    python scripts/test_ha/run.py journal          # what the fake received
    python scripts/test_ha/run.py doctor           # is this instance ours, up

`start` keeps the ports (TEST_HA_PORT, TEST_FAKE_PORT) and the interpreter
(HA_PYTHON) in TEST_HA_DIR/instance.json for every later command.
    python scripts/test_ha/run.py token            # a fresh access token

DUMP defaults to `navizone.json` beside this file : a HUB Navizone and its
three rooms, from a real dump with the names and ids replaced and no absence
set. Home Assistant runs from `.venv-ha` (or HA_PYTHON), the version
`requirements_test.txt` pins ; the frontend and the default integrations'
requirements are installed by Home Assistant itself on first start. State
lives in TEST_HA_DIR (default `.test-ha`), which `start` wipes.
"""

import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
WORK = pathlib.Path(os.environ.get("TEST_HA_DIR", ROOT / ".test-ha")).resolve()
CONFIG = WORK / "config"
VENV = ROOT / ".venv-ha"
DEFAULT_DUMP = HERE / "navizone.json"

# Another test HA on the machine may already hold the defaults, so the ports
# and the interpreter are chosen at `start` and kept in WORK for every later
# command.
INSTANCE = WORK / "instance.json"
SAVED = json.loads(INSTANCE.read_text()) if INSTANCE.exists() else {}
PYTHON = os.environ.get("HA_PYTHON") or SAVED.get(
    "python", str(VENV / "bin" / "python")
)
HA_PORT = int(os.environ.get("TEST_HA_PORT") or SAVED.get("ha_port", 8123))
HA_URL = f"http://127.0.0.1:{HA_PORT}"
FAKE_PORT = int(os.environ.get("TEST_FAKE_PORT") or SAVED.get("fake_port", 8765))
FAKE_URL = f"http://127.0.0.1:{FAKE_PORT}"
CLIENT_ID = HA_URL + "/"

REAL_API = "https://apis.groupe-atlantic.com"

OWNER = {"name": "Test", "username": "test", "password": "test-password"}

CONFIGURATION = """\
homeassistant:
  time_zone: Europe/Paris
  country: FR
  language: fr
  unit_system: metric

default_config:

logger:
  default: warning
  logs:
    custom_components.cozytouch: debug
"""


def http_store(port):
    return {
        "version": 2,
        "minor_version": 2,
        "key": "http",
        "data": {
            "stable": {
                "server_port": port,
                "cors_allowed_origins": ["https://cast.home-assistant.io"],
                "login_attempts_threshold": -1,
                "ip_ban_enabled": True,
                "ssl_profile": "modern",
                "use_x_frame_options": True,
                "created_at": "2026-01-01T00:00:00+00:00",
                "error": None,
                "error_message": None,
            },
            "pending": None,
            "yaml_migration_done": True,
        },
    }


def request(method, path, body=None, form=None, token=None, base=HA_URL):
    """One HTTP call, JSON in and out, exiting on anything but 2xx."""
    data, headers = None, {}
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            raw = response.read()
    except urllib.error.HTTPError as err:
        raise SystemExit(
            f"{method} {path} answered {err.code}: {err.read().decode()[:500]}"
        ) from err
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return raw.decode()


def wait_for(url, seconds):
    """Until the URL answers with anything but a 404, or give up."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=10)
            return
        except urllib.error.HTTPError as err:
            if err.code != 404:
                return
        except OSError:
            pass
        time.sleep(2)
    raise SystemExit(f"{url} did not come up within {seconds}s ; see {WORK}/*.log")


def spawn(name, argv):
    """Start a process detached from this one, its output in WORK/<name>.log."""
    log = open(WORK / f"{name}.log", "ab")  # noqa: SIM115 -- the child keeps it
    # Not from the repository : `python -m` puts the working directory on the
    # path, and its `custom_components` would shadow the patched copy.
    # S603: argv is built here from this interpreter and this repository.
    process = subprocess.Popen(  # noqa: S603
        argv,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        cwd=WORK,
    )
    (WORK / f"{name}.pid").write_text(str(process.pid))


def kill(name):
    pidfile = WORK / f"{name}.pid"
    if not pidfile.exists():
        return
    pid = int(pidfile.read_text())
    try:
        os.killpg(pid, signal.SIGTERM)
        for _ in range(30):
            os.kill(pid, 0)
            time.sleep(1)
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except PermissionError:
        # macOS refuses a signal to a group whose leader is a zombie waiting
        # for a parent that has not reaped it : the process is already gone.
        pass
    pidfile.unlink()


def copy_integration():
    """The working tree's integration, talking to the fake instead of Atlantic."""
    target = CONFIG / "custom_components" / "cozytouch"
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(
        ROOT / "custom_components" / "cozytouch",
        target,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    const = target / "const.py"
    text = const.read_text()
    if REAL_API not in text:
        raise SystemExit("const.py no longer names the API address this replaces")
    const.write_text(text.replace(REAL_API, FAKE_URL))


def start_ha():
    if not pathlib.Path(PYTHON).exists():
        raise SystemExit(f"No Home Assistant interpreter at {PYTHON} ; run setup")
    spawn("hass", [PYTHON, "-m", "homeassistant", "-c", str(CONFIG)])
    # The API answers before startup is over ; onboarding only once the
    # default integrations are set up, which on a first start includes
    # installing their requirements.
    wait_for(HA_URL + "/api/", 900)
    wait_for(HA_URL + "/api/onboarding", 900)


def onboard():
    """Create the owner and finish onboarding ; keep a refresh token."""
    code = request(
        "POST",
        "/api/onboarding/users",
        {**OWNER, "client_id": CLIENT_ID, "language": "fr"},
    )["auth_code"]
    tokens = request(
        "POST",
        "/auth/token",
        form={"grant_type": "authorization_code", "code": code, "client_id": CLIENT_ID},
    )
    (WORK / "tokens.json").write_text(json.dumps(tokens))

    access = tokens["access_token"]
    request("POST", "/api/onboarding/core_config", {}, token=access)
    request("POST", "/api/onboarding/analytics", {}, token=access)
    request(
        "POST",
        "/api/onboarding/integration",
        {"client_id": CLIENT_ID, "redirect_uri": CLIENT_ID},
        token=access,
    )


def access_token():
    tokens = json.loads((WORK / "tokens.json").read_text())
    return request(
        "POST",
        "/auth/token",
        form={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": CLIENT_ID,
        },
    )["access_token"]


def add_account():
    """The config flow, as the UI would run it : account, then every device."""
    token = access_token()
    flow = request(
        "POST", "/api/config/config_entries/flow", {"handler": "cozytouch"}, token=token
    )
    step = request(
        "POST",
        f"/api/config/config_entries/flow/{flow['flow_id']}",
        {"username": "fake@example.com", "password": "fake"},
        token=token,
    )
    if step.get("type") == "form" and step.get("step_id") == "devices":
        step = request(
            "POST",
            f"/api/config/config_entries/flow/{flow['flow_id']}",
            {"create_unknown": False, "dump_json": False},
            token=token,
        )
    if step.get("type") != "create_entry":
        raise SystemExit(f"The config flow stopped at {step}")


def setup():
    """The venv Home Assistant runs from, at the version the tests pin."""
    pin = re.search(
        r"^homeassistant==(\S+)", (ROOT / "requirements_test.txt").read_text(), re.M
    )
    if pin is None:
        raise SystemExit("requirements_test.txt pins no homeassistant")
    uv = shutil.which("uv") or "uv"
    subprocess.run(  # noqa: S603 -- fixed arguments
        [uv, "venv", "-q", "--python", "3.14.2", str(VENV)], check=True
    )
    subprocess.run(  # noqa: S603 -- fixed arguments
        [
            uv,
            "pip",
            "install",
            "-q",
            "--python",
            str(VENV / "bin" / "python"),
            f"homeassistant=={pin.group(1)}",
        ],
        check=True,
    )
    print(f"Home Assistant {pin.group(1)} in {VENV}")


def start(dump):
    kill("hass")
    kill("fake")
    shutil.rmtree(WORK, ignore_errors=True)
    CONFIG.mkdir(parents=True)
    INSTANCE.write_text(
        json.dumps(
            {
                "ha_port": HA_PORT,
                "fake_port": FAKE_PORT,
                "dump": str(pathlib.Path(dump).resolve()),
                "python": PYTHON,
            }
        )
    )
    (CONFIG / "configuration.yaml").write_text(
        CONFIGURATION + f"\nhttp:\n  server_port: {HA_PORT}\n"
    )
    # From 2026.9 the YAML port is only a trial, reverted unless confirmed ;
    # the same port already stable in storage leaves nothing to try.
    (CONFIG / ".storage").mkdir()
    (CONFIG / ".storage" / "http").write_text(json.dumps(http_store(HA_PORT)))

    spawn(
        "fake",
        [
            PYTHON,
            str(HERE / "fake_atlantic.py"),
            str(pathlib.Path(dump).resolve()),
            "--port",
            str(FAKE_PORT),
        ],
    )
    wait_for(FAKE_URL + "/fake/journal", 30)

    copy_integration()
    start_ha()
    onboard()
    add_account()
    print(f"Home Assistant is up on {HA_URL}, owner {OWNER['username']}")


def restart():
    kill("hass")
    copy_integration()
    start_ha()
    print(f"Restarted on {HA_URL}")


def states(text=""):
    for state in request("GET", "/api/states", token=access_token()):
        entity = state["entity_id"]
        if text not in entity:
            continue
        attributes = state["attributes"]
        shown = {
            key: attributes[key]
            for key in ("hvac_action", "preset_mode", "preset_modes")
            if key in attributes
        }
        print(entity, "=", state["state"], shown or "")


def call(service, data="{}"):
    domain, name = service.split(".", 1)
    result = request(
        "POST", f"/api/services/{domain}/{name}", json.loads(data), token=access_token()
    )
    print(json.dumps(result, indent=1, ensure_ascii=False))


def device(entity):
    deviceId = request(
        "POST",
        "/api/template",
        {"template": "{{ device_id('%s') }}" % entity},  # noqa: UP031
        token=access_token(),
    )
    if not deviceId or deviceId == "None":
        raise SystemExit(f"{entity} has no device")
    print(f"/config/devices/device/{deviceId}")


def doctor():
    """Whether this instance is ours, up, and serving the integration."""
    if not INSTANCE.exists():
        raise SystemExit(f"No instance in {WORK} ; run start")
    for name in ("hass", "fake"):
        pidfile = WORK / f"{name}.pid"
        pid = int(pidfile.read_text()) if pidfile.exists() else None
        try:
            os.kill(pid, 0) if pid else None
        except ProcessLookupError:
            pid = None
        print(f"{name}: {'pid ' + str(pid) if pid else 'NOT RUNNING'}")
    token = access_token()
    version = request("GET", "/api/config", token=token)["version"]
    print("home assistant:", version, HA_URL)
    entries = request(
        "GET", "/api/config/config_entries/entry?domain=cozytouch", token=token
    )
    print("cozytouch entry:", ", ".join(e["state"] for e in entries) or "NONE")
    print("dump:", SAVED["dump"])
    served = request("GET", "/fake/journal", base=FAKE_URL)
    print("fake:", FAKE_URL, len(served), "requests")


def journal():
    for line in request("GET", "/fake/journal", base=FAKE_URL):
        print(line)


def main():
    args = sys.argv[1:]
    commands = {
        "setup": (setup, 0, 0),
        "start": (start, 0, 1),
        "restart": (restart, 0, 0),
        "stop": (lambda: (kill("hass"), kill("fake")), 0, 0),
        "states": (states, 0, 1),
        "call": (call, 1, 2),
        "device": (device, 1, 1),
        "journal": (journal, 0, 0),
        "doctor": (doctor, 0, 0),
        "token": (lambda: print(access_token()), 0, 0),
    }
    if not args or args[0] not in commands:
        raise SystemExit(__doc__)
    function, least, most = commands[args[0]]
    rest = args[1:]
    if not least <= len(rest) <= most:
        raise SystemExit(__doc__)
    if args[0] == "start" and not rest:
        rest = [str(DEFAULT_DUMP)]
    function(*rest)


if __name__ == "__main__":
    main()
