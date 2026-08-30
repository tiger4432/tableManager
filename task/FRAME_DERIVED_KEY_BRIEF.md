# Frame-aware seats, via a key the walk DERIVES and never writes

Owner ruling 2026-08-30, in their words:

> 「원래 원장은 append only 였잖아 이걸 해석해서 가상 엣지는 못하나」
> 「자꾸 뭐 덕지덕지하지 말고 근본 원리 하나로 해결할 생각해」
> 「ㅇㅇ 파생키 진행해」

## Destination — written first, and every round is checked against it

**Two logs read the same physical seat in different frames (one at 270°, one at 180°) and
both write columns named `dt_x`/`dt_y`. The walk must treat those two readings as ONE seat,
without the ledger ever asserting that they are the same.**

Done means: a walk that starts on one side reaches the other side's atoms through the seat,
the ledger has not gained a row or lost one, and correcting a frame declaration changes the
answer on the very next walk with nothing to retract.

## The one principle this implements

> **The ledger stores only what a source SAW. "These are the same" is a judgment, not an
> observation, so the walk makes it — at read time, from the declaration.**

Everything below follows from that sentence. Three earlier designs were discarded for
violating it; they are listed under "Do not build" so they are not re-proposed.

## What does NOT change

```
ledger atoms          no write, no supersede, no retraction, no re-translation
vocabulary            no new predicate.  Both sides already emit `transfer@1` into the
                      seat; they meet because the OBJECT becomes one node
entities/sources      no new entity, no new source, no new table
top-level config      no new section.  `ALL_SECTIONS` in setup_bundle.py stays as it is
walk axes             still exactly two: { start , follow }.  No third axis, no toggle
`follow` clause       not one character.  Frames are not predicates, so they are not
                      followable and they do NOT consume a hop
```

## Layer 1 — declaration grammar (`server/ledger/setup_bundle.py`)

Two new fields. Both OPTIONAL; absent means "this has no geometry", which is today's
behaviour for every entity and source that exists now.

```
entities.<type>.frame_keys      key names that form this entity's coordinate.  Declared
                                ONCE per entity, because WHICH keys are the coordinate is
                                a property of the ENTITY, not of each source.

sources.<id>.frame.<type>       that source's transform TO THE DATUM, per entity type:
                                  { "<out_key>": {"from": "<in_key>",
                                                  "sign": <int>, "offset": <int>}, ... }
```

Worked shape — every key name comes from the declaration, never from code:

```json
"entities": { "die@1": { "keys": ["mat_id","x","y","mat_type"],
                         "frame_keys": ["x","y"] } },
"sources":  { "<id>": { "frame": { "die@1": {
                  "x": {"from":"y","sign":-1,"offset":7},
                  "y": {"from":"x","sign": 1,"offset":0} } } } }
```

### Four validator checks — each turns a silent no-op into a refusal

```
V1  every key named in `frame.<type>` (out-keys and `from`s alike) is in that entity's
    `frame_keys`, and the out-key set EQUALS `frame_keys`
    -> a typo is refused instead of quietly transforming nothing
V2  the `from` values are a PERMUTATION of the out-keys
    -> guarantees invertibility, which Half A depends on absolutely
V3  `sign` is +1 or -1 and `offset` is an integer
    -> the walk matches keys with JSONB equality; a float turns 1 into 1.0 and then
       matches nothing, silently
V4  `frame.<type>` names a type this source may speak about, and that type declares
    `frame_keys`
    -> a frame on a geometry-less type is a declaration that can never fire
```

⚠️ `unknown_field` already fires on anything outside the allow-list, so until these two
fields exist the declaration above is REFUSED at load. That fixes the order: grammar first,
then declaration, then walk.

## Layer 2 — the walk (`server/ledger_api/ledger_subgraph.py`)

Symmetric, two halves. **Landing one half looks like it works and connects nothing** — Half B
alone only merges what the walk already reached; Half A alone breaks the fetch.

### Reading the declaration — `_declared_frames()`

Sits beside the existing `_declared_key_order()` and copies its shape: open the ontology
config once, cache, key by source id.

🔴 **ONE DELIBERATE DIFFERENCE.** `_declared_key_order` documents that an absent or
unreadable declaration "leaves every label exactly as it is today rather than taking the walk
down with it." For a label that is right — the worst case is an ugly label. For a transform it
is wrong: the worst case is *silently connecting nothing*, which on screen is identical to *no
frame declared yet*. So `_declared_frames()` records whether the read succeeded and how many
sources declared a frame, and Layer 3 puts that in the response.

### Half A — going down: expand the frontier (this is what CROSSES)

At the frontier construction site (`frontier_ids` -> `entity_refs`, which feeds
`claims_for_entities`): for each ref whose type declares `frame_keys`, emit that ref once per
declared frame, with the coordinate run through that frame's INVERSE transform.

```
canonical ref  ──inverse, per declared frame──>  several raw refs  ──> frontier
```

The SQL matches `e.subject_keys = f.keys` against RAW stored keys, so a frontier carrying
canonical keys matches nothing. `follow` and `direction` pass through untouched.

Only types with `frame_keys` expand. Everything else is passed through exactly as today — do
not infer "has coordinates" from key names.

### Half B — coming up: build the node in the datum

Inside `_expand_atom`, immediately before each `_entity_node(...)` call — there are two, the
subject arm and the target arm — take `atom.source_who`, look up that source's frame for that
entity type, and run the coordinate FORWARD to the datum. Keys the declaration does not name
pass through unchanged.

The seed node built at walk start needs no transform: the caller's ids came from a previous
canonical response, so they are already in the datum, and Half A inverts them on the way down.

`source_who` is already carried — it is `context.source_plan.source_id` from
`ledger/roleframe.py`, is already in `ATOM_COLUMNS`, and is already attached to the edge.
**No new plumbing.**

## Layer 3 — visibility, not a gate

The owner rejected a gate. Nothing is blocked; the response simply says what happened:

```
how many sources contributed atoms about frame-bearing types, and how many of those
declared a frame
whether the declaration file was read at all
```

An undeclared source is treated as already-in-the-datum — the same behaviour as today, so
nothing regresses. But it must be COUNTED, because "no frame declared", "frame declared
wrongly" and "declaration unreadable" otherwise render as the same screen.

## Stop conditions — stop and report, do not improvise

```
S1  the frontier is built in more than one place
    -> Half A would have to be repeated, and a missed site crosses frames on some hops and
       not others.  STOP and report the sites
S2  `_expand_atom` builds an endpoint node anywhere other than those two `_entity_node`
    calls -> same reason.  STOP and report
S3  the entity spec in setup_bundle.py has no place for an optional field without
    restructuring its validator -> STOP.  Adding a field must not become a validator rewrite
S4  any existing test asserts on a node id for a frame-bearing type
    -> those ids move by design.  STOP and list them; the ruling on each is the lead's
```

## Verification

```
G1  server/tests/test_ledger_setup_bundle.py   grammar accepts the two new fields, and
                                               V1..V4 each REFUSE with a named code
G2  server/tests/test_ledger_subgraph.py       with NO frame declared, every existing
                                               assertion holds unchanged  <- no-regression
G3  new, in test_ledger_subgraph.py            two sources, one carrying a 90° frame, both
                                               speaking about one physical seat: the walk
                                               returns ONE seat node and BOTH sides' edges.
                                               Then change the declared frame and assert the
                                               answer changes with NO ledger write
G4  the same fixture with the frame declaration REMOVED must return TWO seat nodes
    🔴 G3 without G4 passes even if the transform is a no-op and the two sides happened to
       share coordinates.  G4 is the discriminating input, not a duplicate of G3
```

Interpreter: `C:/Users/kk980/anaconda3/envs/assy_manager/python.exe -m pytest` (conda run
hangs). Run only these two files — not the suite.

## Do not build — each was proposed and discarded today, with the reason

```
⛔ frame in the node identity key    the frame comes from a row a person can correct, and
                                    correcting it would move every node id.  Identity takes
                                    only what the row itself knows and cannot change
⛔ reader/equipment in the key       same defect, and the owner states the frame is not a
                                    property of the equipment
⛔ a `same_seat` predicate written   writing "these are the same" makes our own error a
   into the ledger                  permanent record and brings retraction back
⛔ unifying the two sides' names     this was the lead's own first proposal and it is what
                                    CREATED the problem: it makes the LEDGER assert sameness
⛔ a gate that verifies alignment    explicitly rejected: 「게이트에 박지 말고」
⛔ a user-facing frame toggle        fails the standing test (not a predicate, not a node ->
                                    do not make an axis).  Frames are always crossed
```

## Boundaries the lead has NOT resolved — do not decide these in-lane

```
B1  the live declaration is the OWNER's file.  This lane touches
    `server/config/sample/ledger_config.json.sample` ONLY, and in the SAME commit as the
    grammar, so the shipped sample never lags a guard the live file has.
    Do NOT write `server/config/ontology/ledger_config.json`
B2  whether production's two readings also differ in `mat_id`.  If they do, this mechanism
    lands correctly and still connects nothing, because a rotation cannot compute one name
    from another.  That is a question for the owner, NOT a reason to widen this lane
B3  saved markings on frame-bearing types will not match derived ids.  Count them after
    landing and report; do not migrate them
```
