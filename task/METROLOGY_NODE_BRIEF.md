# Stand the metrology up as nodes — owner ruling 2026-08-30

The owner ruled that metrology becomes a node, and named the shape themselves a month
earlier. `docs/spec/ONTOLOGY_GRAPH_SPEC.md` §7.5b, "함수형 온톨로지 (사용자 명명)":

```
(입력 노드들) -[INPUT_TO]-> 함수노드 -[PRODUCED]-> (출력 노드들)

MetrologyEvent: (WaferState_in) → (WaferState_out, MetroResult)
owner correction 2026-07-25: 「모든 이벤트는 상태 전이 함수다 — 계측도 예외 아님」
the spec marks this "G3.5 설계 — 아직 물화되지 않음". This round materialises it.
```

`INPUT_TO` / `PRODUCED` are the retired graph's vocabulary. Do **not** resurrect those
spellings. Today the world is 「엔티티 · 어휘 · walk」 and the shape is expressed as declared
entities and declared predicates. The spec supplies the SHAPE, not the names.

---

## Why two nodes and not one — this is the part that was got wrong once already

The lead's first draft keyed one node as `(wafer, step, eqp, eventtime)`. That is a real
grouping, but it is **per wafer**, so a control wafer's metrology is a DIFFERENT node from a
marked wafer's. Reach can then never coincide across seeds and the denominator this whole
round exists to produce would read 0 forever.

So the shared thing has to be separate from the event:

```
metrology_station@1   keys {step, eqp}                      63 nodes   SHARED   -> the denominator
metrology_run@1       keys {wafer, step, eqp, occurred_at}  24,070     per wafer -> the event
```

Measured on the live ledger 2026-08-30 (`process_param_num`, 73,275 rows):

```
distinct param_id                 73,275   == row count. param_id is a ROW ID, not a place.
                                  shape: <row uuid>:<role>:<param>
                                  DO NOT put it in either key — it collapses the grouping.
distinct (step, eqp)                  63   step 12 · eqp 31
distinct (wafer, step, eqp, time) 24,070
params per (wafer,step,eqp,time)  1 -> 8,164 groups · 2 -> 1,800 · 3 -> 24 · 4 -> 9,541 · 5 -> 4,541
                                  two thirds carry several params, so the spec's signature
                                  「one metrology, several results」 is真 in this data
stations per wafer                1 -> 2,007 wafers · 5 -> 766 · 6 -> 2,387 · 7 -> 22
```

**Do not key the station `(step, eqp, param)`** (that is 136). Reaching such a node means the
value exists, so the denominator becomes equal to the numerator and says nothing. The `param`
must be left out; that is exactly what makes it a denominator.

---

## What to declare

```
entities  metrology_station@1   keys ["step", "eqp"]           class: static
          metrology_run@1       keys ["wafer", "step", "eqp", "occurred_at"]

vocabulary
          performed@1   wafer  -> metrology_run       (the spec's INPUT_TO)
          at@1          run    -> metrology_station
          produced@1    run    -> quantity            (the spec's PRODUCED)
```

`class: static` on the station is deliberate and matches `quantity@1` / `recipe@1`, which are
already static. It has a declared consequence, and the brief states it rather than hiding it:
policy ④ forbids static→dynamic, so **「같은 자리에서 잰 다른 웨이퍼」 will not walk** from a
station. That is the same trade the spec already recorded for `dt_eqp` ("노드로 만들면 degree
768 허브 하나가 생기고 … 무관한 칩 768개로 되확장"). If you conclude the station must be
dynamic instead, STOP and report — that is a lead ruling, not an implementation choice.

## Where the rows come from — nothing new

The standing rule is 「표에 원천 데이터를 넣고, 그걸로 원장」 and it is **already satisfied**.
`process_param_num` carries `row_id · business_key_val · param_id · wafer_id · step · param ·
value · value_text · role · unit · eqp_id · recipe_id · eventtime`, and two sources already
read it:

```
process_param_num_measure   relation process_param_num   map.unit {"kind":"row"}
process_param_txt_measure   relation process_param_txt   map.unit {"kind":"row"}
```

Both are **row unit**, which is why the multi-key entities here do not hit the wall `in_slot`
hits on `lot_event` (that source is event unit). `die@1` already has four identity keys and
works on row-unit sources, so four keys is not new ground.

So: **no new table, no new source, no reload of anything.** Add the two entities, the three
predicates, and three mappings on the two existing sources.

🔴 `store.write_batch` has exactly one legitimate caller, `ledger/runtime_v2.py`. If you find
yourself wanting a script to write atoms, stop — the answer is a declaration, and here the
declaration is all this round is.

## Leave `measures@1` alone

`wafer -measures-> quantity` stays exactly as it is. Whether it later becomes derivable from
`performed/produced` is a separate question and not this round's. Adding the new path while
the old one stands is intentional: both statements are true, and removing one is a ruling.

---

## Verify

State the seed and the arguments with every number you report.

```
① the station is shared
   walk from wafer ZZ-DOE-BW-01 (+ ZZ-DOE-BW-02) against negatives ZZ-DOE-BW-03, ZZ-DOE-BW-04
   direction=both hops=6
   expect: the SAME station node reached from both sides — measured today, both groups
           sit at step CMP · eqp ZZ-EQP-01 · role actual
   so slurry_A_ml should read reach [2,0] with the station reading [2,2]
   ⚠️ report what you actually get. Do not adjust anything to produce this number.

② a quantity whose station the control never entered reads [0,0] on the station

③ no regression
   claims/hops on an existing wafer seed before and after, same arguments both times

④ tests: only the ones that measure what you touched
   interpreter C:/Users/kk980/anaconda3/envs/assy_manager/python.exe -m pytest (conda run hangs)
```

## Sample

🔴 The live `server/config/ontology/ledger_config.json` is gitignored; only
`config/sample/ledger_config.json.sample` is tracked. **Change both in the same commit**, and
verify by parsing the two files and diffing them field by field — a declaration that lives
only in the live file ships a guard that is switched off, and that has happened here before.

## Stop conditions — report, do not decide

```
- `occurred_at` will not canonicalise as an identity key (a timestamp in a key is untried here;
  the last multi-key move died on row canonicalisation, on numpy bool_ and then NaN).
  If it fails: STOP. Do not invent a surrogate key.
- the station has to be dynamic rather than static
- the walk's node budget is materially eaten by 24,070 run nodes
- `measures@1` starts double-counting anything in the contrast
```

## Scope

```
DO      the declaration (entities, vocabulary, mappings) on live AND sample
DO      re-translate the two sources so the atoms exist, through the normal path
DON'T   touch the client. The denominator's consumer is a separate round
DON'T   invent projection node types or edges — declared entities and predicates only
DON'T   `git add -a` / `-A`; explicit paths on both add and commit; `git commit -F <file>`
```

Report: what you declared, the atom counts per new predicate, the four verifications with
their seeds, and the field-by-field live↔sample comparison.
