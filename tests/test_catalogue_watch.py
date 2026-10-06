"""What the catalogue watcher does with an answer from Atlantic.

The watcher is a script, not part of the integration, and it runs unattended
twice a month against a live account. Both halves fail silently: a reshuffled
list would open an issue saying 405 capabilities changed, and a truncated
answer would rewrite the file with the rest deleted.
"""

import importlib.util
import pathlib
import subprocess
import sys

import pytest

SCRIPT = (
    pathlib.Path(__file__).resolve().parent.parent
    / "scripts"
    / "check_capability_catalogue.py"
)


@pytest.fixture
def watcher(tmp_path):
    """The script, with its catalogue files pointed at temporary ones."""
    spec = importlib.util.spec_from_file_location("catalogue_watch", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.CATALOGUES = {
        route: (tmp_path / f"{route}.jsonl", 300) for route in module.CATALOGUES
    }
    module.token = lambda: "token"
    return module


def items(count: int = 400, **edits) -> list[dict]:
    built = [
        {"id": i, "name": f"CAP_{i}", "type": 5, "unit": None, "enum": None}
        for i in range(1, count + 1)
    ]
    for index, value in edits.items():
        built[int(index)] = {**built[int(index)], **value}
    return built


def test_an_unchanged_catalogue_says_so(watcher):
    watcher.catalogue = lambda token, route: items()
    assert watcher.main() == watcher.CHANGED  # first run, the file did not exist
    assert watcher.main() == 0


def test_the_api_reordering_its_answer_is_not_a_change(watcher):
    watcher.catalogue = lambda token, route: items()
    watcher.main()
    watcher.catalogue = lambda token, route: list(reversed(items()))
    assert watcher.main() == 0


def test_a_new_id_is_a_change(watcher):
    watcher.catalogue = lambda token, route: items()
    watcher.main()
    watcher.catalogue = lambda token, route: [
        *items(),
        {"id": 999999, "name": "BRAND_NEW", "type": 5, "unit": None, "enum": None},
    ]
    assert watcher.main() == watcher.CHANGED


def test_a_renamed_id_is_a_change(watcher):
    watcher.catalogue = lambda token, route: items()
    watcher.main()
    watcher.catalogue = lambda token, route: items(**{"3": {"name": "RENAMED"}})
    assert watcher.main() == watcher.CHANGED


def test_a_truncated_answer_is_refused_rather_than_written(watcher):
    watcher.catalogue = lambda token, route: items()
    watcher.main()
    before = watcher.CATALOGUES["capabilities"][0].read_text()
    watcher.catalogue = lambda token, route: items(count=10)
    assert watcher.main() == watcher.UNREACHABLE
    assert watcher.CATALOGUES["capabilities"][0].read_text() == before


def test_one_truncated_catalogue_writes_neither(watcher):
    watcher.catalogue = lambda token, route: items()
    watcher.main()
    watcher.catalogue = lambda token, route: (
        items(count=10) if route == "models" else items(**{"3": {"name": "NEW"}})
    )
    assert watcher.main() == watcher.UNREACHABLE
    assert "NEW" not in watcher.CATALOGUES["capabilities"][0].read_text()


def test_a_new_model_alone_is_a_change(watcher):
    watcher.catalogue = lambda token, route: items()
    watcher.main()
    watcher.catalogue = lambda token, route: (
        items(count=401) if route == "models" else items()
    )
    assert watcher.main() == watcher.CHANGED


def test_it_loads_without_home_assistant():
    """The runner has no aiohttp and no homeassistant, and never will.

    The script reaches into the integration for two constants. Importing the
    package to get them runs its `__init__`, which imports aiohttp -- so the
    first scheduled run did nothing but traceback, and exited 1, which the
    workflow read as "the catalogue changed". Hence issue #144, and hence the
    exit code for changed being 10.

    The test suite cannot see this on its own : its own environment has both.
    So the script is loaded in a subprocess that refuses them.
    """
    blocked = (
        "import sys, importlib.abc, importlib.util\n"
        "class Deny(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] in {'aiohttp', 'homeassistant', 'voluptuous'}:\n"
        "            raise ImportError(name)\n"
        "        return None\n"
        "sys.meta_path.insert(0, Deny())\n"
        f"spec = importlib.util.spec_from_file_location('w', {str(SCRIPT)!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "assert module.COZYTOUCH_ATLANTIC_API.startswith('https://')\n"
        "assert module.COZYTOUCH_CLIENT_ID\n"
    )
    # S603: the program is this file's own literal, and the interpreter is
    # the one running the suite.
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-c", blocked], capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr


def test_changed_is_not_the_code_python_uses_for_a_crash():
    spec = importlib.util.spec_from_file_location("catalogue_watch", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.CHANGED != 1
    assert module.UNREACHABLE != 1
