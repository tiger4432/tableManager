# Declaration patch — `server/config/ontology/ledger_config.json` (implementer, 2026-08-26)

Per the Lead PM's ruling ③, the implementer does not write the live declaration. This file is
the patch: which key becomes what, quoted against the live file's current contents. The live
file was read to quote it exactly and was never opened for writing.

**Apply order matters**: change ③ needs the view from
`server/scripts/create_bonding_core_die_view.py` to exist first, or `bonded_from` reads a
relation that is not there.

---

## ① `entities` — add one seat type

**Path** `entities`

```json
+  "lot_slot@1": { "keys": ["lot", "slot"] }
```

No other entity changes. `die@1` already keys on `[mat_id, x, y, mat_type]`, and `"DTLotSlot"`
is a **value** bound in a mapping (change ③), not something `entities` declares — the working
example `dt_transfer / core-die-to-dt-die` binds `"Wafer"` and `"DT"` the same way.

Per the plan §2-bis, `lot_slot@1` carries **no time in its key**. Order rides on the edge.

---

## ② `sources.lot_event.bind.mappings.in_slot` — the seat holds the wafer

**Path** `sources.lot_event.bind.mappings.in_slot.bind.subject`

Before (live):
```json
"subject": {
  "approval_status": "approved", "kind": "entity", "entity_type": "lot@1",
  "keys": { "lot": { "approval_status": "approved", "kind": "column", "column": "lot" } }
}
```
After:
```json
"subject": {
  "approval_status": "approved", "kind": "entity", "entity_type": "lot_slot@1",
  "keys": {
    "lot":  { "approval_status": "approved", "kind": "column", "column": "lot"   },
    "slot": { "approval_status": "approved", "kind": "column", "column": "slots" }
  }
}
```
Then **delete** the now-duplicated qualifier, because the seat is the subject rather than a note
about it (plan §4 ⑤ — a qualifier holds no identifier):
```json
-  "slot": { "approval_status": "approved", "kind": "column", "column": "slots" }
```
`target` is untouched: `wafer@1{wafer: wafers}`. Predicate stays `has_wafer@1`.

`slots` and `wafers` are the singular names `prepare` produces; the raw table holds
`slot_numbers` and `wafer_ids` as colon-separated lists paired by position (measured: 666
exploded (lot, slot, wafer) rows over 331 wafers).

---

## ③ `sources.bonded_from` — wafer→wafer becomes die→die

### 3a. relation and read

```json
-  "relation": "bonding_core_lot"
+  "relation": "bonding_core_die"
```
```json
"read": {
  "unit": "row",
-  "identity":  ["base_id", "core_wafer"],
+  "identity":  ["base_id", "bx", "by"],
   "group_by":  [],
-  "order_by":  ["base_id", "core_wafer"],
+  "order_by":  ["base_id", "bx", "by"],
-  "cursor":    { "columns": ["base_id", "core_wafer"] },
+  "cursor":    { "columns": ["base_id", "bx", "by"] },
   "occurred_at": { "column": "event_time", "timezone": "Asia/Seoul" }
}
```
`(base_id, bx, by)` identifies a row exactly: 371,593 rows, 371,593 distinct triples.

### 3b. `map.input_columns` and `prepare.input_columns` — both lists, identically

```json
-  ["base_id", "core_wafer", "core_slot", "event_time"]
+  ["base_id", "bx", "by", "dt_seat", "dt_x", "dt_y", "event_time"]
```

### 3c. the mapping itself

**Rename** `bonded-wafer-from-core-wafer` → `bonded-die-from-dt-seat`. The old name describes a
target that no longer exists; the Lead PM already expects this source's atom ids to change
wholesale because the relation changed.

```json
"bonded-die-from-dt-seat": {
  "predicate": "bonded_from@1",
  "bind": {
    "occurred_at": { "kind": "column", "column": "event_time" },
    "subject": {
      "kind": "entity", "entity_type": "die@1",
      "keys": {
        "mat_id":   { "kind": "column",   "column": "base_id" },
        "x":        { "kind": "column",   "column": "bx" },
        "y":        { "kind": "column",   "column": "by" },
        "mat_type": { "kind": "constant", "value":  "Wafer" }
      }
    },
    "target": {
      "kind": "entity", "entity_type": "die@1",
      "keys": {
        "mat_id":   { "kind": "column",   "column": "dt_seat" },
        "x":        { "kind": "column",   "column": "dt_x" },
        "y":        { "kind": "column",   "column": "dt_y" },
        "mat_type": { "kind": "constant", "value":  "DTLotSlot" }
      }
    }
  }
}
```
The `core_slot` qualifier is **dropped** — the old relation's column is gone, and the core side
now travels as its own segment.

`dt_seat` is `dt_lot || '|' || dt_slot`, composed in the view: `mat_id` takes one column and the
grammar offers only `column` and `constant`, so a two-column identity has to arrive as one
column. 2,632 distinct seats.

---

## 🔴 ④ `merge_slot_join` / `split_slot_carry` — **NOT in this patch. I was wrong earlier.**

I reported these as fixable in the declaration alone. That was read off column *presence*. Read
off the *content*, they are not:

```
today   "from" and "to" BOTH bind the same column `slots`
        subject and target BOTH bind the same column `lot`
        -> a slot change cannot be written down at all; 443 atoms collapse to 46 x 49
row     lot=CL-2601-002-A4  child_lot=CL-2601-005-A5  slots=01:05:07…  wafers=WF.010201:…
        the counterparty's SLOT for that wafer is not on this row
```
The move is recoverable, but only by pairing the two `lot_event` rows on wafer id — a relation,
not a binding. Measured:
```
paired seat-to-seat edges                97
   of which the slot actually CHANGES    21   <- exactly the 21 the plan cites
today's slot_map atoms                  443   (46 subjects x 49 objects, one pair 25 times)
```
So the honest shape is a second relation (`lot_slot_move`: from_lot, from_slot, to_lot, to_slot,
wafer, event_time) with these two mappings binding `lot_slot@1 -> lot_slot@1` over it. That is a
relation the order did not name, so it is proposed rather than built. **Ruling requested.**

Without it the split/merge segment of the target walk stays shut, and the 21 real moves remain
unrepresentable.

---

## ⑤ `sources.lot_slot_move` — NEW source (added after the Lead PM approved the relation)

Requires `server/scripts/create_lot_slot_move_view.py` to have been applied.

🔴 **One mapping, not two.** `merge_slot_join` and `split_slot_carry` both emit `slot_map@1`
from the same rows; over one relation that would write every move **twice**. The view does not
distinguish a merge from a split and does not need to — a move is a move, and the lots'
own names say which direction it went.

```json
"lot_slot_move": {
  "relation": "lot_slot_move",
  "read": {
    "unit": "row",
    "identity":  ["from_lot", "from_slot", "to_lot", "to_slot", "wafer"],
    "group_by":  [],
    "order_by":  ["event_time", "from_lot", "from_slot", "to_lot", "to_slot", "wafer"],
    "cursor":    { "columns": ["event_time", "from_lot", "from_slot", "to_lot", "to_slot", "wafer"] },
    "occurred_at": { "column": "event_time", "timezone": "Asia/Seoul" }
  },
  "map": {
    "implementation_id": "declarative-role", "implementation_version": 1,
    "input_columns": ["from_lot", "from_slot", "to_lot", "to_slot", "wafer",
                      "event_time", "event_type"],
    "unit": { "kind": "row" }
  },
  "prepare": {
    "accepts_verified_join_rules": false,
    "implementation_id": "direct-join", "implementation_version": 1,
    "inherit_virtual_join_rules": [],
    "input_columns": ["from_lot", "from_slot", "to_lot", "to_slot", "wafer",
                      "event_time", "event_type"],
    "output_columns": {}
  },
  "bind": {
    "mappings": {
      "seat-to-seat": {
        "predicate": "slot_map@1",
        "bind": {
          "occurred_at": { "kind": "column", "column": "event_time" },
          "subject": {
            "kind": "entity", "entity_type": "lot_slot@1",
            "keys": {
              "lot":  { "kind": "column", "column": "from_lot"  },
              "slot": { "kind": "column", "column": "from_slot" }
            }
          },
          "target": {
            "kind": "entity", "entity_type": "lot_slot@1",
            "keys": {
              "lot":  { "kind": "column", "column": "to_lot"  },
              "slot": { "kind": "column", "column": "to_slot" }
            }
          },
          "event_type": { "kind": "column", "column": "event_type" }
        }
      }
    }
  }
}
```

**`event_type` IS a qualifier, and must be.** The source records split / merge / track_in; an
earlier draft dropped it because "the lot names say which way it went", which is a derivation
standing in for a record. It is the move's property, not an identifier, so the qualifier is
where it belongs -- the same seat `bonded_from` used for `core_slot`. Measured after carrying
it: 135 of 135 rows typed, split 85 / merge 50.

**No `wafer` qualifier.** Plan §4 ⑤: a qualifier holds no identifier, and if the name exists as
a node the fact is an edge. The wafer link is already an edge — change ② makes `in_slot` emit
`lot_slot@1 --has_wafer--> wafer@1`, so the seat says which wafer it holds and the move says
where the seat went.

## ⑥ `sources.lot_event.bind.mappings` — delete the two that cannot say what they mean

```json
-  "merge_slot_join":  { … }
-  "split_slot_carry": { … }
```
Both are replaced by ⑤. Left in place they would keep writing the collapsed shape (443 atoms,
46 subjects x 49 objects, one pair 25 times) alongside the real one.

`descent`, `first_sight_holder`, `first_sight_item` and `in_slot` stay.


---

# REVISION 2 (2026-08-26 afternoon) — `bonded_from` splits into two facts

The first version pointed `bonded_from` at the DT seat, which quietly changed what the predicate
MEANS: "this BW came from that core wafer" became "this BW die sits in that DT seat". Core
lineage disappeared with it. Per the Lead PM's ruling, the relation carries two facts and they
get two mappings and two predicates.

`bonding_core_die` now also provides `core_seat` (`core_lot||'|'||core_slot`) and `core_wafer`,
the latter through a DEDUPED lookup: `SELECT DISTINCT core_lot, core_slot, wafer_id`. Measured
before relying on it -- 355 pairs, 78,555 rows, and ZERO pairs naming two different wafers, so
the fan-out was duplication rather than ambiguity. The row count stayed at 371,593, which is the
proof that nothing was squashed.

## ③-a REPLACE the single mapping with TWO

`sources.bonded_from.map.input_columns` and `.prepare.input_columns` (both):
```json
["base_id", "bx", "by", "core_wafer", "cx", "cy", "dt_seat", "dt_x", "dt_y", "event_time"]
```

`sources.bonded_from.bind.mappings` -- replace `bonded-die-from-dt-seat` with:

```json
"bonded-die-from-core-die": {
  "predicate": "bonded_from@1",
  "bind": {
    "occurred_at": { "kind": "column", "column": "event_time" },
    "subject": {
      "kind": "entity", "entity_type": "die@1",
      "keys": {
        "mat_id":   { "kind": "column",   "column": "base_id" },
        "x":        { "kind": "column",   "column": "bx" },
        "y":        { "kind": "column",   "column": "by" },
        "mat_type": { "kind": "constant", "value":  "Wafer" }
      }
    },
    "target": {
      "kind": "entity", "entity_type": "die@1",
      "keys": {
        "mat_id":   { "kind": "column",   "column": "core_wafer" },
        "x":        { "kind": "column",   "column": "cx" },
        "y":        { "kind": "column",   "column": "cy" },
        "mat_type": { "kind": "constant", "value":  "Wafer" }
      }
    }
  }
},
"<NAME THE LEAD PM GIVES>": {
  "predicate": "<NEW PREDICATE>@1",
  "bind": {
    "occurred_at": { "kind": "column", "column": "event_time" },
    "subject": {
      "kind": "entity", "entity_type": "die@1",
      "keys": {
        "mat_id":   { "kind": "column",   "column": "base_id" },
        "x":        { "kind": "column",   "column": "bx" },
        "y":        { "kind": "column",   "column": "by" },
        "mat_type": { "kind": "constant", "value":  "Wafer" }
      }
    },
    "target": {
      "kind": "entity", "entity_type": "die@1",
      "keys": {
        "mat_id":   { "kind": "column",   "column": "dt_seat" },
        "x":        { "kind": "column",   "column": "dt_x" },
        "y":        { "kind": "column",   "column": "dt_y" },
        "mat_type": { "kind": "constant", "value":  "DTLotSlot" }
      }
    }
  }
}
```
The vocabulary needs the new predicate declared with `die@1` on both sides, and `bonded_from@1`
keeps `die@1 -> die@1` as revision 1 already set it.

## ⚠️ ONE THING THE PATCH CANNOT DECIDE — the core side is NULL on most rows

```
rows in the relation                     371,593
   with cx,cy (a core die recorded)       93,118   (25.1%)
   with a core WAFER resolved             18,545   (5.0%)
distinct (core_lot,core_slot) in view        657
   resolved through core_wafer_map           128   <- 529 pairs have no map row
```
`bonded-die-from-core-die` can only speak for the rows that carry a core wafer. What the
framework does with the other 278,475 -- refuse the molecule, mark it incomplete, or write a
null-keyed atom -- is not something I can read out of the declaration, and guessing it would put
a wrong shape into the ledger. **It shows up as `refused_molecules` / `incomplete_molecules` on
the first reload; if it refuses, the mapping needs its own relation.**

📌 The gate the ruling asks for is already reachable in the data: the owner's seed
`SYN-BW-101-16` resolves **29 distinct core wafers** in the new view -- the same 29 the old
`bonding_core_lot` gave.
