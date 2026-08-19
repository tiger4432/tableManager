# The skeleton — the ledger config's shape, as a document we keep

Owner ruling, 2026-08-20 night: **「관리문서 = 스켈레톤」**, and 「현재 생성 계층 키로 받아다가
스켈레톤에서 목적 객체 형태 받아가지고」, 「지금 ledger_config 만들어둔거 좀 쳐내면 되겠네」.

So the skeleton is not a cache and not a derivation. It is **the managed document that says what a
ledger config is made of**, and the form is generated from it.

---

## Rule 0 — this is the no-hardcoding principle, and it sets the finish line

Owner, the last thing he said before sleeping: **「스켈레톤은 결국 하드코딩 금지 원칙과 일맥상통함」.**

His standing definition of done for that principle is not "the code reads a config" — it is
**「다른 스키마 운영 환경에서 코드 0줄, 선언 교체만으로 발화」**. Applied here, that is sharper
than "the form renders from the skeleton", and it is what makes the round checkable:

> **Add a field to the skeleton and the form offers it, with zero lines of client change.
> Remove one and the form stops offering it. Same for a whole section.**

Which forbids one thing outright: **no per-kind branch anywhere in the form.** Not for packs, not
for sources, not "just for `emit`". The moment the renderer asks *which kind is this*, the next
schema needs code again, and the skeleton has become a config-shaped hardcode.

Walk it before reporting: put a junk optional field into the skeleton, reload, see it on screen,
take it out again. That walk is 30 seconds and it is the only proof that the wiring is real —
「착지는 배선이 아니다」.

---

## Destination

**A person rebuilds `lot-lineage@1` — all four claims, exactly — using only the form.**
Then `dt-job@1`. Then the same for the other six kinds.

This is the acceptance test because it is the walk that failed tonight. Not 「칸이 뜬다」.

---

## Why this exists — measured, not argued

The screen currently holds a hand-copied table of the grammar (`client2/src/ontology_shapes.js`,
`EMIT_SHAPE`). Walked in the owner's browser tonight, it was already wrong:

| the validator says | the screen offers |
|---|---|
| `emit.object` required `kind`, optional `entity` · `value` · `qualifiers` | `kind` · `value` |

`lot-lineage@1` uses `entity` and `qualifiers` in **3 of its 4 claims**. So the owner's own live pack
could not be expressed, and nothing anywhere was red about it. A second author of a contract drifts
in silence — that is the same failure this screen already removed once, for closed lists.

## Where the truth already is

**The validator states the field names as literal tuples, in 25 places.** Measured in
`server/ledger/setup_bundle.py`:

```python
397   bundle             required=("setup_version", *LOGICAL_SECTIONS) optional=OPTIONAL_SECTIONS
978   packs.<id>         required=("claims",)
988   …claims.<id>       required=("roles", "emit")
998   …roles.<name>      required=("kind", "required")  optional=("allowed_binding_kinds", "allowed_values")
1037  …emit              required=("predicate", "subject", "object", "occurred_at")
1044  …emit.object       required=("kind",)  optional=("entity", "value", "qualifiers")
1065  profiles.<id>      required=("source", "packs", "mappings")
1077  …mappings[]        required=("mapping_id", "use", "bind")  optional=("sentence",)
1166  sources.<id>       required=("relation", "driver", "profile_id")
1171  …driver            required=("unit", "identity", "group_by", "order_by", "occurred_at", …)
1201  …driver.occurred_at required=("timezone",)  optional=("column", "basis")
…     (25 sites in total; 32 required=/optional= tuples)
```

and the closed lists are already published — `config_authoring.closed_lists()`, whose docstring is
the standing rule: *"The screen renders what this returns and owns no copy."*

**So nothing here is being invented. It is being collected into one document and published.**

---

## Rule 1 — one author, and the second author is audited mechanically

The skeleton is the document. The validator stays the only thing that decides whether a declaration
is good. They must not drift, so **the skeleton is checked against those 25 tuples, and the check
prints a number.**

```
fields the validator names, that the skeleton does not carry   ->  must be 0
fields the skeleton carries, that the validator never names    ->  must be 0
```

🔴 **Report both numbers.** Not "checked" — the counts. A skeleton drafted by trimming the live
config will pass the first check for everything the two live packs happen to use and **quietly miss
every optional field nobody has used yet** — which is tonight's failure moved one level up. The
count is what makes that impossible to miss.

Trimming the live config is the right way to *draft* it — fast, concrete, and it would have caught
`qualifiers`. It is not the way to *finish* it.

## Rule 2 — three node kinds, and no fourth

```
record   fixed field names        { fields: [ {key, required, …} ] }
map      operator-NAMED keys      { of: <node> }        claims.<id> · roles.<name> · qualifiers.<name>
leaf     a value                  { hint: … }
```

`map` is the one that matters and the one a naive shape misses. `claims`, `roles`,
`emit.object.qualifiers`, `profiles.*.mappings` members are named by the person, not by the grammar.
The screen already has this control — an id input + a 「+」 button — from claims and roles. Reuse it;
do not invent a second one.

🔴 **A `map` control is add AND remove, and it is one control, not two features.** Owner, walking
the screen himself at 00:40: **「팩 폼에서 역할 삭제가 안되네」**. Counted in the live DOM —
`add-claim` 1, `add-role` 1, `delete-declaration` 1, and **`remove-claim` 0, `remove-role` 0,
`remove-qualifier` 0**. Everything a person names can be created and never taken back.

Today that is survivable only because the raw JSON editor is still there, and **that editor is
being removed in step 5.** Ship the remove with the map node or the screen becomes a trap on the
day the door closes: a typo in a role name would be permanent. This is the same shape as the
`lot` entity dead end from the 19th — something namable that nothing could unname.

Removal is a draft edit like any other: drop the key, let the validator say what that broke. It
refuses nothing, and it asks nothing beyond the single confirm the screen already uses for a
declaration.

## Rule 2-b — 🔴 EVERY node is CRUD-complete. No exceptions, no "later"

Owner, 2026-08-20: **「폼은 모두 crud 가능해야함」**. This is the declaration-level ruling
(「버튼은 생성, 편집, 저장, 삭제 4가지만 · crud!」) applied one level down, to the form's
interior — and it replaces deciding this node by node.

Read it off the node kind, not off the field name:

| node | C | R | U | D |
|---|---|---|---|---|
| `map` | name a member | the members are listed | edit inside it | **remove that member** |
| `record` | — (its fields are fixed) | rows | type a value | **clear the field** |
| `list` | add an item | items | edit an item | remove that item |

🔴 **D on a `record` field means REMOVING THE KEY, not writing `""`.** An optional field set to
an empty string is not absent — it is present and blank, which the validator refuses
(`must be a non-blank string`). If clearing a box leaves `""` behind, the person has no way back
to "I never set this", and that is a one-way door on every optional field in the config.

🔴 **Required fields stay on screen after D.** Clearing one does not delete a row; it returns to
`missing`, which is exactly what that state is for. Only optional fields disappear from the
document, and their row stays offered because the skeleton — not the document — is what says the
field exists. This is the whole reason the skeleton is worth building: a form driven by what the
document HOLDS can never offer back what you just removed.

Nothing beyond the four letters. No rename control (delete + create covers it, and a rename
would silently orphan every `$role` that pointed at the old name), no reordering, no undo.

## Rule 3 — leaf hints name a source, never a value

```
ref     <section>     a declaration in that section   -> datalist from the DOCUMENT's keys
role                  a `$role` of the enclosing claim -> datalist from sibling roles
choice  <list key>    a key of closed_lists()          -> select
free                  text
```

🔴 **No closed list is copied into the skeleton.** `choice` names the key; the values stay on the
server, exactly as `closed_lists()` requires today.

🔴 **`ref` candidates come from the declaration document, not the compiled bundle** — picker spec §0.
Pulled from the compiled result, every list goes empty precisely while a config is being built up,
which is the interpreter behaviour the owner rejected.

🔴 **`predicate` is a `ref` to `vocabulary`, and this is the field the whole picker spec was written
for.** A predicate name lands in atom identity (`schema.py:58` `DEDUPE_COLUMNS`), so `regsiter@1`
beside `register@1` splits one meaning in the ledger forever, and neither is refusable. Tonight it
rendered as a bare textbox with no suggestions.

## Rule 4 — a guide, not a gate

Saving is unchanged: **any valid JSON saves**, and what does not resolve stays listed as `invalid`.
The skeleton decides what the form OFFERS. It never refuses, never rewrites a value, and never
decides a type — the validator does that, and it now says so on the screen.

Rendering must never change the file: a value already in the document is always among the options,
recognised or not, and an absent value shows as absent, not as the first choice.

## Rule 5 — it rides the payload that already arrives

The client already fetches `/authoring/schema` and reads it as `state.authoringSchema`
(`closed_lists()` is what fills it). **Add one key to that payload.** No new endpoint, no new
request, no new client fetch path.

## Rule 6 — the form has ONE operation

The owner's words: 「현재 생성 계층 키로 받아다가 스켈레톤에서 목적 객체 형태 받아」.

```
shapeAt(path) -> node        // walk the skeleton by the path being edited
render(node)  -> form        // record -> rows;  map -> named members + add;  leaf -> control
```

Recursive, and that recursion is what covers **all seven kinds at every depth** instead of seven
hand-written forms. When the authoring plan HAS a row for a path, keep preferring it — that row
carries the candidates and the refusals. The skeleton fills what the plan cannot see, which is
everything absent.

`EMIT_SHAPE` is deleted by this round, not extended.

---

## Order

1. **The role bug first** — it is five minutes and nothing can be walked until it is gone.
   `ontology_explorer.js:754` passes a declaration-relative path to `draftValueAt`, the
   absolute-path reader, which therefore always answers `undefined`; the handler then rewrites the
   whole `roles` object and **every earlier role is deleted, silently, with its kind and required.**
   `editShapeAtPath` builds missing branches now, so the fix is to drop the two-branch dance:
   `editShapeAtPath(\`claims.${claimId}.roles.${roleId}\`, {})`.
   🔴 `add-claim` (line 741) reads the parsed draft directly and is **correct** — measured. Do not
   "fix" it too. And check `draftValueAt`'s other caller passes an absolute path; a reader that
   answers `undefined` for a path it cannot parse is what made this silent.

2. **Define the components.** Owner: 「ledger config 각 구성 요소 구성 제대로 파악 및 정의하고」.
   Draft by trimming the live config, then run the Rule 1 audit and close every hole it counts.

3. **Publish it** on the existing `/authoring/schema` payload.

4. **Generate the form** from it — `shapeAt(path)`, all seven kinds.

5. Then the screen-cleanup items and the raw-JSON removal, in that order.

## Regression lines — write these, not the easy ones

- **role survival**: after adding role N, roles 1..N−1 are still present **and still carry their
  `kind` and `required`**. Assert an earlier role's `kind` by value. "A role appeared" is the
  assertion that let tonight's defect through.
- **skeleton vs validator**: the two counts from Rule 1, asserted as 0. This is the line that keeps
  the second author honest after everyone has forgotten why it exists.
- **the walk**: `lot-lineage@1` rebuilt through the form equals the live declaration, key for key.
  Compare the parsed objects, not the text.

## Out of scope tonight

Styling. The owner's UI mockup arrives in the morning and CSS work now is thrown away.

## Housekeeping

Delete every declaration you create, in the session you create it. The owner's config carried
`adf` and `asdfds` all night, one of them invalid, with 14 refusal lines in his sidebar.
Correct fingerprint: **vocabulary 5 · entities 3 · packs 2 · preparers 2 · mappers 2 · profiles 2 ·
sources 2.**
