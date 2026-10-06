---
name: pr-description
description: Write or rewrite a pull request description so it is short and actually readable. Use when opening a PR, editing a PR body, or when the user says "PR description", "describe this PR", "gh pr create", or complains a PR body is too long.
---

# pr-description

A PR body is read once, in a hurry, on a phone. The diff is already on the
page. The body exists to say why, not to narrate what the reader can see.

## Shape

Three blocks, in this order, nothing else:

```markdown
<one sentence: the observed behaviour that made this necessary>

## What changed
- <one line>
- <one line>

## How to check
<one command, or one click path>
```

`What changed` is 2 to 5 bullets. If it needs six, the PR is two PRs — say so
to the user and stop.

`How to check` is one runnable thing. `pytest tests/test_x.py -q`, or
"open the device page, the eco preset is gone". Not a checklist.

## Title

One sentence, present tense, what changed for the person using the thing.
No `feat:`, no ticket number, no scope prefix.

- Good: `Stop offering an eco mode the room air conditioners do not have`
- Bad: `fix(ac): remove eco preset`

## Hard limits

- 150 words total. Count them.
- No tables, no emoji, no nested bullets, no collapsible sections.
- No "Summary", "Overview", "Notes", "Testing" headings beyond the two above.
- No restating the diff. No file-by-file walkthrough.
- No screenshots unless the change is visual.

## Where the words come from

The commit message body already says why. Reuse it, trimmed — do not write
fresh prose that says the same thing differently.

## Before posting

Delete, in this order:
1. Any sentence that starts "This PR".
2. Any sentence explaining what a reviewer could read in the diff.
3. Any hedge that carries no uncertainty.

Then check: reading only the first line and `How to check`, does the reviewer
know why this exists and how to verify it? If yes, post it.

## This repo

Pull requests target `mathieuletyrant/cozytouch-hacs`, base `main`.

`How to check` is normally `.venv/bin/pytest tests/ -q`, or the one test file
the change touches. A docs-only PR still says so, with `ruff check .`.
