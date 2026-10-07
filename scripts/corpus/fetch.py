#!/usr/bin/env python3
"""Download every capability capture the tracker holds.

Reporters paste their setupviewv2 into an issue -- attached as a file, or
inline in the body or a comment. This pulls both into one directory so
extract.py can walk it.

    python3 fetch.py <outdir>

Needs `gh` authenticated. Files land as <outdir>/*.json; the inline ones are
raw markdown with a .json name, which extract.py copes with -- it never parses
strictly. Nothing is cleaned here: redaction happens in extract.py, so the
originals stay comparable to what is on GitHub.
"""

import json
import pathlib
import re
import subprocess
import sys

REPO = "gduteil/cozytouch"
FILE_URL = re.compile(r"https://github\.com/\S+?\.json")


def gh(path):
    out = subprocess.run(  # noqa: S603 -- arguments built here, not read from input
        ["gh", "api", "--paginate", path],  # noqa: S607 -- whichever gh is authenticated
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout)


def main(outdir):
    out = pathlib.Path(outdir)
    out.mkdir(parents=True, exist_ok=True)

    owner = REPO.split("/")[0]
    issues = gh(f"/repos/{REPO}/issues?state=all&per_page=100")
    comments = gh(f"/repos/{REPO}/issues/comments?per_page=100")

    sources = [(f"{owner}-i{it['number']}", it.get("body") or "") for it in issues]
    for c in comments:
        issue = c["issue_url"].rsplit("/", 1)[1]
        sources.append((f"{owner}-c{issue}-{c['id']}", c.get("body") or ""))

    inline = attached = 0
    for tag, body in sources:
        if "capabilityId" in body:
            (out / f"body-{tag}.json").write_text(body)
            inline += 1
        for url in sorted(set(FILE_URL.findall(body))):
            name = f"file-{tag}-{url.rsplit('/', 2)[-2]}.json"
            got = subprocess.run(  # noqa: S603 -- a github.com URL matched above
                # S607: the system curl.
                ["curl", "-sL", "--max-time", "30", "-o", str(out / name), url],  # noqa: S607
                capture_output=True,
            )
            if got.returncode == 0 and (out / name).stat().st_size > 500:
                attached += 1
            else:
                (out / name).unlink(missing_ok=True)

    print(f"{inline} captures inline, {attached} files attached -> {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "dumps")
