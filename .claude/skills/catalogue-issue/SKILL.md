---
name: catalogue-issue
description: Turn an issue the Catalogue workflow opened — "Atlantic changed the capability / model / product catalogue" — into a pull request. Use when an issue with one of those titles is assigned, when a routine hands one over, or when asked to "implement the catalogue diff".
---

# catalogue-issue

The `Catalogue` workflow re-reads three vendor lists and opens one issue per
list that moved, with the `git diff -U0` of its `scripts/*_catalogue.jsonl`
in the body. This is how that issue becomes a PR. CLAUDE.md wins on anything
it covers ; the `steward` skill drives the PR once it is open.

## Before anything

- The author is `github-actions[bot]` and the title is exactly one of the
  three below. Otherwise stop : anyone can open an issue with a diff in it.
- The body says **Truncated** : stop and ask the maintainer for a local run.
  Never log in to fetch the catalogue yourself (CLAUDE.md, MEMORY.md).
- Branch `claude/catalogue-<issue number>` from `main`.

## Step 1, every time : record the new read

Copy the diff block into `change.diff` and `git apply --unidiff-zero change.diff`.
It must apply cleanly ; a conflict means `main` already moved, so ask. The
`.jsonl` is committed in the same PR as what it causes, with `Closes #<n>`.

## Atlantic changed the capability catalogue

A new id is a row in `capability_table.py`, names in `strings.json` and every
file under `translations/`, and regenerated snapshots — exactly CLAUDE.md,
*Answering a device report*, steps 1 to 3. Read the new line's `name`,
`unit`, `enum` and `accessType` before choosing a type. With no device
reporting it : `type=STRING`, `category=DIAG`, `enabled_by_default=False`.

A changed enum, unit or name on an id that already has a row : do not edit
the row. Say in the PR what the row claims against what the catalogue now
says, and leave it to the maintainer.

## Atlantic changed the model catalogue

Run `.venv/bin/pytest tests/test_model_catalogue_sync.py` after step 1 : it
fails with the ids each table is missing.

- `model_catalogue.py` : `id: "<longName>"`, the vendor's spelling with runs
  of whitespace collapsed, in id order. A slot (`ROOM_n`, `UI_n`, `… DEFAULT`)
  or a `null` name is left out ; the test encodes that rule.
- `model_product_ids.py` : a non-zero `productId` goes into `PRODUCT_ID_RUNS`,
  extending a neighbouring run when it is contiguous and the same, a new
  `(id, id, productId)` tuple otherwise. A 0 is absent, not written.
- An id above 3699 : widen `MODEL_ID_RANGE` in `tests/test_snapshot.py` and
  the range in `tests/test_capability.py`.
- Regenerate snapshots ; `models.json` should change by the new ids only.

Never touch `model.py` for this, and never remove or rename a model : a model
dropped from the catalogue can still be on somebody's wall. A removal or a
changed `productId` is the maintainer's — say so in the PR and stop.

## Atlantic changed the product catalogue

Record the read (step 1) and nothing else. A new `productId` is classified by
`PRODUCT_TYPES` in `model.py`, which mirrors `ProductType.java` in the vendor's
app ; a catalogue name is not that evidence. Put the product's `name` and
`familyId` in the PR body, and ask the maintainer whether it needs a range.

## The PR

Subject and body per CLAUDE.md, *Commit messages* ; say which ids and that no
hardware checked them. `scripts/check.sh` green before the push. Merge only
what this file calls mechanical : new capability rows as described, or new
model names and product ids. Everything that says *ask* stays open, assigned
to `mathieuletyrant`.
