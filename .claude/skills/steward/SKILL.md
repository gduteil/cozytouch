---
name: steward
description: How to drive a pull request on this repository to mergeable — CI fixes, review comments, snapshots, what to ask the maintainer. Read before acting on a CI or review event on a PR Claude opened or was asked to drive.
---

# steward

The session's own rules say *that* a PR gets driven to green. This says how,
here. CLAUDE.md still wins on anything it covers.

## Before any push

`scripts/check.sh`. CI runs the same three checks ; a push that has not passed
them locally is a guess.

## Branches

- A `claude/**` branch Claude created : bring `main` in by merge, not rebase,
  once the PR is open — the maintainer may have it checked out.
- Never push to `main`.

## CI red

- `pytest` failing in `tests/test_snapshot.py` : read the snapshot diff first.
  Regenerate (`UPDATE_SNAPSHOTS=1 .venv/bin/pytest tests/test_snapshot.py`)
  only when the diff is exactly what the PR meant to change, and say so in
  the commit body. A snapshot change the PR did not intend is the bug.
- `tests/test_sensor_values.py` pins strings as they are : an output change
  updates its test in the same commit.
- `pytest (HA … on Python 3.13.7)`, the floor job, failing alone : syntax or
  an API newer than the floor. Fix the code ; raising the floor is the
  maintainer's call (CLAUDE.md, *Tests*).
- `ruff` : fix the code, never disable a rule. The rules that are off are off
  for reasons in `pyproject.toml`.

## Review comments

- Nits, renames, a missing translation, a test : do them.
- Anything touching `model.py` `OVERRIDES`, a capability's meaning, or the
  HA floor : reply with the evidence and ask. These are measured facts, not
  style, and a review is not a capture.
- A reviewer proposing something MEMORY.md lists as *Rejected* : reply with
  the line and its evidence, do not implement.

## Ask the maintainer

- Anything that would log into the real Cozytouch account.
- A release, a tag, a `manifest.json` bump.
- A change that can only be checked on hardware other than the HUB Navizone
  (1758), its rooms (557-561) or THZONE (1505-1507) : say it is unverified,
  in the PR body.

## Commits and the PR body

Subject and body as CLAUDE.md, *Commit messages*. One commit per round of
fixes, not one per comment.

When a round changes what the PR does, not only how, rewrite its body with
the `pr-description` skill ; a body that still describes the first push is
wrong, not just stale.
