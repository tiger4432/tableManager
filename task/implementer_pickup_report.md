# Implementer report — 2026-08-20, the form becomes generated

## The destination, and whether it was reached

> A person rebuilds `lot-lineage@1` — all four claims, exactly — using only the form.

**Reached, and walked.** An isolated config root (port 8099, temp) was seeded with the live
declarations minus that one pack. The pack was then rebuilt in a browser through the form
alone — four claims, sixteen roles with their kinds and required flags, four emits including
three `entity_ref` objects and four qualifiers — and saved.

```
pack landed in the file                     : True
differences against the live declaration    : 0
validator complaints about the rebuilt pack : 0
```

**Which state was walked:** an unsaved, newly created pack. Built all the way down, saved
once at the end. No save in between.

## 🔴 The owner's server must be restarted

The screen now reads the form's shape from `skeleton` on `/authoring/schema`. A backend that
booted before `1754f6f` does not send that key, and the form does not appear at all — the
screen falls back to the old bucket list. It does not break; it just shows none of tonight's
work.

## The three walls, and what each turned out to be

1. **The second role deleted the first.** `add-role` asked `draftValueAt` whether a `roles`
   map existed and rewrote the whole map when it said no — but that reader takes an ABSOLUTE
   path and was handed a relative one, so it answered `undefined` every time. Fixed in
   `a36691e` by dropping the branch: `editShapeAtPath` builds its own parents.
2. **`emit.object.entity` existed nowhere.** Not in the authoring plan (measured: the plan
   emits `object.kind` and `object.qualifiers.*` and never `object.entity`) and not in the
   screen's hand-written shape. Three of the four claims need it.
3. **`emit.object.qualifiers.*` was produced and then swallowed.** The plan does emit those
   rows — `membership` gets `slot`, `slot_map` gets `from`/`to`/`wafer` — but every row of a
   claim left the state buckets to travel with the claim block, and the block did not draw
   them, so they appeared nowhere.

## What replaced the hand-written form

`ledger_skeleton.json`, beside the validator, published on the payload the screen already
fetches. Three node kinds — `record`, `map`, `leaf` — plus `{use}` for the one recursive
shape (a binding holds bindings under its identity keys).

The renderer asks what the NODE is and never what the declaration is. Three builders that
knew `claims`, `roles`, `emit`, `mappings` and `pack` by name are gone. CRUD comes off the
node kind: a `map`'s members can be named and removed, which is every place a person coins a
name — claims, roles, qualifiers, mappings, entity keys.

## The audit, and what it caught

```
fields the validator names, that the skeleton does not carry : 0
fields the skeleton carries, that the validator never names   : 0
```

The pairing (which call site is which node) is declared in the test; the field names are
read out of the validator's syntax tree. A call site with no pairing fails rather than skips.

Both findings were on my side, not the document's. A reader that understood only literal
tuples under-reported the validator — and an under-reporting reader accuses the other side:
it reported the skeleton as having invented `suggestion_reason`, which the validator does
name, one indirection away. And the "no closed list is copied" check first counted values,
so three `when` gates naming three different binding kinds looked like a copied list.

## Decisions taken, flagged for the fork

* **`mappings` is index-keyed, not name-keyed.** The spec put it with the operator-named
  maps; in the live config it is a JSON array (`mappings[0].use`). Handled with
  `keyed_by: name | index` on the same node kind rather than a fourth kind.
* **A `flag` hint was added** for booleans (`required`, `enabled`). Without it a checkbox
  cannot be data-driven and a text box writes the string `"true"`.
* **`when` names one value** to gate a field on a sibling `kind`. It never hides a value the
  document already holds.

## Not done

* A controller-level harness for role survival. None exists — the existing harnesses drive
  the store and the view, not the click handlers. Tonight's evidence is the browser walk.
* The fork's "one gap" message arrived truncated and has not been read.
* doc-keeper counter at 91.
