# The skeleton — the ledger config's shape, as a document we keep

Owner ruling, 2026-08-20 night: **「관리문서 = 스켈레톤」**, and 「현재 생성 계층 키로 받아다가
스켈레톤에서 목적 객체 형태 받아가지고」, 「지금 ledger_config 만들어둔거 좀 쳐내면 되겠네」.

So the skeleton is not a cache and not a derivation. It is **the managed document that says what a
ledger config is made of**, and the form is generated from it.

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
