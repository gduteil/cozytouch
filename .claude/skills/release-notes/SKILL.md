---
name: release-notes
description: Write release_notes/<version>.md for a Cozytouch release — what the release means for somebody running it, in their words, with a section emoji per theme. Use when the user says "release notes", "/release-notes 2026.9.21", "je vais release", or asks to prepare or rewrite a release.
---

# release-notes

The release page is the only thing most people ever read about this
integration. They are standing in HACS looking at an update button, deciding
whether to press it. The page has to answer that, and nothing else.

The version is whatever the user gave you. No version given, ask — do not
guess the bump.

## Gather

```bash
PREVIOUS=$(git describe --tags --abbrev=0)
git log --no-merges --format='%h %s' $PREVIOUS..HEAD
```

Commit subjects are written for this repo, so they already say what changed
in the present tense. They are your index, not your text. Read the bodies of
anything you cannot translate into a user-visible effect:

```bash
git log --no-merges $PREVIOUS..HEAD -- <path>
git show <sha>
```

A commit whose only effect is internal — a refactor, a test, a doc — does
not get a line. It is already in the folded commit list.

## Write

One file, `release_notes/<version>.md`. No title and no version number: the
release page puts both above it.

Open with one sentence saying what this release is about. Then a section per
theme, in the order somebody cares about them:

1. what now works that was broken
2. what devices now do that they could not
3. what reads better than it did
4. what only matters if you are reporting a device

Each section is a `### 🔧 Heading` and a short paragraph. Prose, not bullets
— a bullet list of eleven capability names is the commit list again, and
that is already on the page, folded.

## The emoji

One per section heading, and it has to mean something:

| | |
| - | - |
| 🔧 | a fix — something was broken, it is not any more |
| 🌡️ | devices doing more : new sensors, new controls |
| 🏷️ | naming — models, capabilities, values that read as words now |
| 📋 | schedules and programs |
| 🔍 | diagnostics, device reports, what a maintainer needs |
| ⚠️ | something that will change under the reader's feet |

No emoji inside a paragraph, none in the opening sentence. A page where
every line has a sticker reads as marketing, and this is a page people check
before letting something touch their heating.

## Voice

Write to one person who owns the hardware. "Your boiler", not "users'
boilers". Say what they will see in Home Assistant, in the words the
Home Assistant UI uses.

Be specific and be honest about the edges. "631 model ids that used to read
as `Unknown product` are named" beats "improved device support", and if a
fix only lands on one model family, name the family. If a thing is still
broken and somebody will hit it, say so — that is what ⚠️ is for.

Never thank anybody for their patience, never call a release exciting, and
never end on a line about what is coming next.

## Length

Around 200 words. Four sections is plenty ; six is too many, and means two
of them are the same theme. A release with one real change gets one
paragraph and no headings at all.

## Finish

Write the file, show it to the user, and say what you inferred rather than
read — they own the hardware and will catch a claim that is too strong.

Then remind them of the two steps left: merge the pull request carrying this
file and the `manifest.json` bump, then dispatch the release workflow with
the version.
