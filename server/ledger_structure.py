# -*- coding: utf-8 -*-
"""`GET /api/ledger/structure` — the ontology at TYPE level, GENERATED and never drawn.

🔴 WHY THIS ENDPOINT EXISTS (product owner, 2026-08-14, `SCENARIO_CONSOLE_BRIEF`
§0-quater)
--------------------------------------------------------------------------------
> 「지금 너무 구조가 숨겨져 있어서 UI 어떻게 설계해야 할지 모르겠어. 일단 온톨로지
> 구조가 드러나게 하나 만들어줘.」

The ledger's structure today lives in three places that never meet on a screen: the
closed vocabulary (`server/ledger/vocabulary.py`), the translator declarations
(`ledger_config.json`), and 84,747 atoms in a partitioned table. An operator can read
any one of them and still not be able to say what is connected to what, or where the
data actually is. This endpoint answers both questions in one call.

**It is the TYPE level, not the instance level.** No lot, no wafer, no void appears here.
The nodes are entity TYPES and the edges are (subject type, predicate, object) triples.
`GET /api/ledger/trace` is the instance-level screen and this one is deliberately its
complement.

🔴 THE FAILURE CONDITION, NAMED SO IT CANNOT BE ARGUED WITH LATER
------------------------------------------------------------------
> 「하드코딩된 노드/엣지 목록이 응답 어디에든 보이면 실패입니다.」

So there is no list of nodes and no list of edges anywhere in this file. Both halves are
GENERATED:

  * the DECLARED half from `vocabulary.ENTITY_TYPES` x `vocabulary.PREDICATES` — adding a
    predicate to the vocabulary puts an edge on the screen and costs nothing here;
  * the OBSERVED half from one `GROUP BY` over `ledger_events` — a source that starts
    emitting a shape nobody declared appears as an `undeclared` edge rather than being
    silently dropped.

The two halves are then merged, which is the whole point: an edge in the declaration and
not in the data is `declared_only`, and an edge in the data and not in the declaration is
`undeclared`. Those are the two answers a hand-drawn picture can never give.

The only literals in this module are the LABELS of things the vocabulary does not name —
the four resolution classes, the three object kinds — and each falls back to its raw
identifier for a value it has never seen, so a new one is rendered in English rather than
dropped.

🔴 ZERO IS AN ANSWER; `null` IS A DIFFERENT ANSWER
----------------------------------------------------
> 「건수 0인 선언 엣지를 숨기지 마십시오. 0은 「선언은 있는데 데이터가 없다」는
> 답이고, 그게 이 화면이 존재하는 이유의 절반입니다.」

`atoms: 0` means it was counted and there is nothing (`edge_state: "declared_only"`).
`atoms: null` means nobody counted — the ledger relation is not deployed
(`edge_state: "unmeasured"`). Rendering those the same is this project's own
`absent-zero-is-not-inert-zero` lesson, paid for once already.

Every edge and node therefore carries ONE structured word the client branches on:

    flowing              declared AND carrying atoms
    declared_only        declared, counted, zero atoms      <- the honest empty axis
    undeclared           atoms exist for a shape the vocabulary does not declare <- drift
    unmeasured           nothing was counted (relation absent)
    declared_unconsumed  declared, and NOTHING reads it     <- the mechanism layer

The client never has to compute that from a count, which is the R-2026-08-13-C rule
(a fact the screen branches on is a field, not an inference from prose or arithmetic).

🔴 THE PICTURE HAS TWO LAYERS (lead PM, 2026-08-14)
----------------------------------------------------
`graph.layers` enumerates them and the client renders whichever it is given:

  * **ledger** — `graph.nodes` / `graph.edges`, the type graph above.
  * **mechanism** — `graph.mechanism`, the M4 causal model, same field names so ONE
    renderer serves both.

The second layer is here for the same reason the first one is: the tracking UI's ruling
gate is about to become the mechanism graph's FIRST consumer, and the owner has to be
able to see, today, whether that axis is「선언됐지만 아무도 안 읽는다」. It turns out to
be worse than that and the response says so rather than filling in — see
`mechanism_layer`.

[SCALE — and this one is honest rather than reassuring]
--------------------------------------------------------
A type-level census is O(atoms) and there is no way around it: the grouping columns are
`subject_type`, `predicate`, `object_payload->>'type'`, `source_who` and
`source_translator_ver`, and no index carries that combination. One was built and REMOVED
for having no consumer (`schema.INDEXES`'s note on `idx_ledger_type_pred_time`,
64.4 B/atom); it would not serve this query anyway, because it lacks the payload and
provenance columns.

MEASURED on `assy_manager`, 2026-08-14, 84,747 atoms across two monthly partitions,
`CENSUS_SQL` run directly against the live relation, best of five:

    census, whole ledger, with the class breakdown       172 ms   (12 groups)

⚠️ ONE measurement is recorded because one was taken. An earlier revision of this block
carried 85 ms / ~1.0 us/atom / ~10 s, which disagreed with this file's own landing commit
(`3202ac7`: 182 ms, ~2 us/atom, ~20 s) by a factor of two; the remeasurement above agrees
with the commit and the 85 ms figure has been deleted rather than reconciled. A
partition-pruned number is not quoted here because none was taken.

So the request is ~2.0 microseconds per atom, and at the ten-million-atom target that is
~20 s — far past what a page load may spend. The defence is a declared SIZE GATE rather
than a cache:

  * under `FULL_CENSUS_MAX_BYTES` the census covers the WHOLE ledger;
  * above it, a declared window (`LARGE_LEDGER_WINDOW`) is FORCED and the response says
    so in `window.forced` + `window.forced_reason`, so a screen can never quietly show a
    month's counts labelled as all time. Partitioning is monthly, so a windowed census
    prunes to the partitions it needs.

🔴 THE DECLARED HALF IS NEVER WINDOWED. A window scopes COUNTS, never the structure — an
axis declared in the vocabulary is on the screen whatever the window is, at `atoms: 0`.
Otherwise the honest-empty-axis rule above would be defeated by the scale defence.

**No cache, deliberately**, and for the reason `ledger_trace.coverage`'s docstring already
gives for itself: this screen is what an operator opens right after running a backfill,
and a cache would make it answer with the pre-backfill structure at the exact moment its
answer matters most. If a client polls it, the cache belongs there.

🔴 THE RESOLUTION CLASS IS *NOT* COMPUTED IN SQL — THE GROUP KEY IS
--------------------------------------------------------------------------
`ledger_trace.claim_class` is the authority and it is pure Python over one claim. Pulling
84,747 rows into Python to classify them is exactly the whole-table load this project
forbids, so the tempting move is to transcribe the four-arm ladder into a SQL `CASE`.
That was written, measured, and THROWN AWAY — it was slower (285 ms against 152 ms on the
same atoms) and, the reason that actually matters, it was a SECOND SPELLING of a rule that
already has an authority.

What runs instead: every input to `claim_class` except the two payload flags is already a
grouping column, so the flags are lifted INTO the group key (`CENSUS_SQL`, columns 7-8)
and `claim_class` itself is called once per GROUP, on a `CensusClaim` shim. Nothing
re-implements the ladder, so nothing can drift from it. The same argument applies to the
derivation: `ledger_trace.claim_basis` owns the `#<derivation>` suffix and reads the raw
provenance column, which is grouped rather than parsed in SQL. See the block comment above
`CENSUS_SQL` for the full argument and `CensusClaim` for what the shim may carry.

Guarded by `test_ledger_structure_pg.py::test_the_class_breakdown_agrees_with_claim_class`,
which compares the served breakdown against a HAND-WRITTEN expectation (an oracle, not the
implementation checking itself) on a fixture holding at least one atom of EACH class —
including the two that are easy to get wrong: a `#derivation` suffix that is an inference,
and a payload flag that must match JSON `true` rather than any truthy value. It asserts
both class-3 routes fire separately, so it cannot pass with half the resolver working.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

import finding_kinds
import ledger_kinds
import ledger_siblings
import ledger_trace
from ledger_trace import _fetch, relation_exists

logger = logging.getLogger("Ledger.Structure")

LEDGER_RELATION = "ledger_events"
LEDGER_CURSOR_RELATION = "ledger_translator_cursor"

#: Above this on-disk size (summed over the partitions) the whole-ledger census is
#: refused and `LARGE_LEDGER_WINDOW` is forced. 256 MB is ~550,000 atoms at the density
#: measured on this box (486 B/atom on disk), i.e. ~0.55 s of census — the ceiling a
#: page-load call may spend. Same constant and same rule as `ledger_kinds`, one relation
#: over.
FULL_CENSUS_MAX_BYTES = 256 * 1024 * 1024

#: What a too-large ledger is censused over instead. Monthly partitions, so this prunes.
LARGE_LEDGER_WINDOW = "30d"

REASON_LEDGER_TOO_LARGE = "ledger_too_large_for_full_census"

#: `state`, in `GET /api/ledger/coverage`'s three words. One word means one thing across
#: every ledger endpoint, so the console reuses its reading.
STATE_ABSENT = "absent"
STATE_EMPTY = "empty"
STATE_READY = "ready"

#: Per-edge and per-node state. See the module docstring — the client BRANCHES on these.
EDGE_FLOWING = "flowing"
EDGE_DECLARED_ONLY = "declared_only"
EDGE_UNDECLARED = "undeclared"
EDGE_UNMEASURED = "unmeasured"
#: 🔴 The fifth word, and the one the mechanism layer exists to show: DECLARED, and read
#: by NOBODY. `declared_only` means "counted, and the count was zero"; this means there is
#: no count to take, because no predicate, no query and no screen consumes the thing at
#: all. Rendering those two the same would hide the exact state the lead PM asked to make
#: visible — 「선언만 있고 소비자가 0인 축」.
EDGE_DECLARED_UNCONSUMED = "declared_unconsumed"

#: The object kinds' Korean, keyed by the value `vocabulary.OBJECT_KINDS` declares. NOT a
#: list of kinds — an unknown key falls through to the raw identifier below.
OBJECT_KIND_LABELS = {
    "entity_ref": "개체 참조",
    "value": "값",
    "event_ref": "이벤트 참조",
}
#: `register`'s object is ∅ (`object_kind IS NULL`) — see `vocabulary`'s module docstring.
OBJECT_KIND_NONE_LABEL = "없음 (∅)"

#: The four resolution classes, from `ledger_trace.CLASS_NAMES` so the names are not
#: re-spelled here. Labels only.
CLASS_LABELS = {"pin": "핀", "confirmed": "확정", "observation": "관측",
                "inference": "추론"}

#: Origin of a declaration file. `sample` and `code_default` are ANSWERS, not gaps: this
#: project's convention is that `server/config/*.json` is the operator's (gitignored) and
#: `*.json.sample` is what ships, so a screen that cannot tell them apart lets an operator
#: believe they configured something they did not.
ORIGIN_LIVE = "live"
ORIGIN_SAMPLE = "sample"
ORIGIN_CODE_DEFAULT = "code_default"
ORIGIN_ABSENT = "absent"


class StructureError(RuntimeError):
    """The declaration cannot be read at all. A deployment fact, answered as one."""


# --------------------------------------------------------------------------- ids
def _object_token(object_kind, object_type):
    """The third component of an edge id. One spelling, used by both halves of the
    merge — the declared side and the census side MUST agree on it or every edge would
    appear twice, once empty and once full."""
    if object_kind is None:
        return "none"
    if object_kind == "entity_ref":
        return "entity:%s" % (object_type or "?")
    if object_kind == "event_ref":
        return "event"
    return str(object_kind)


def edge_id(subject_type, predicate, object_kind, object_type):
    return "%s|%s|%s" % (subject_type, predicate,
                         _object_token(object_kind, object_type))


def _label(entry, name):
    """A declaration's Korean label, or the raw identifier. NEVER raises: a word added to
    the vocabulary without a label renders in English rather than blanking the screen."""
    return (entry or {}).get("label_ko") or name


def _empty_classes():
    return {name: 0 for name in ledger_trace.CLASS_NAMES.values()}


# ------------------------------------------------------------------- the declared half
def _vocabulary():
    """The closed vocabulary, imported LAZILY.

    🔴 `server/ledger/` is deliberately not on any boot path (`LEDGER_GUIDE` §0: "안 돌아도
    아무것도 안 깨진다 — `server/`에서 `server/ledger`를 import하는 부팅 경로가 없다"), and
    this module is imported by the web server's router. `vocabulary.py` is pure data with
    no imports of its own, so importing it costs nothing — but the guarantee is about the
    BOOT PATH, and keeping the import inside the call keeps it literally true rather than
    almost true.
    """
    try:
        from ledger import vocabulary
    except Exception as exc:                                       # pragma: no cover
        raise StructureError(
            "어휘 선언(server/ledger/vocabulary.py)을 읽을 수 없음: %s" % exc)
    return vocabulary


def declared_edges(vocabulary):
    """Every (subject type, predicate, object) the vocabulary allows. Generated.

    One edge per DECLARED TARGET, not one per predicate: `same_as` accepts six subject
    types and six object types, so it is 36 edges and every one of them is a real thing
    the grammar permits. Collapsing them would be the hand-drawn picture this endpoint
    exists to replace — and `status: "reserved"` is already on each of them, which is the
    field a screen dims them by.
    """
    edges = {}
    for predicate, sig in vocabulary.PREDICATES.items():
        declared_object = sig.get("object")
        for subject_type in sig.get("subject") or []:
            if declared_object is None:
                targets = [(None, None)]
            elif declared_object.get("kind") == "entity_ref":
                types = declared_object.get("types") or sorted(vocabulary.ENTITY_TYPES)
                targets = [("entity_ref", t) for t in types]
            else:
                targets = [(declared_object["kind"], None)]
            for object_kind, object_type in targets:
                eid = edge_id(subject_type, predicate, object_kind, object_type)
                edges[eid] = {
                    "id": eid,
                    "source": subject_type,
                    "target": object_type,
                    "subject_type": subject_type,
                    "predicate": predicate,
                    "predicate_label": _label(sig, predicate),
                    "object_kind": object_kind,
                    "object_kind_label": (OBJECT_KIND_NONE_LABEL if object_kind is None
                                          else OBJECT_KIND_LABELS.get(object_kind,
                                                                      object_kind)),
                    "object_type": object_type,
                    # 🔴 The `value` object's REQUIRED FIELDS, served. This is where
                    # `processed_with` admits that it names an equipment and a recipe
                    # INSIDE a payload rather than as entity refs — which is why
                    # `Equipment` is an isolated node on this graph. The operator can only
                    # see that if the fields are on the wire.
                    "object_fields": list((declared_object or {}).get("required") or []),
                    "qualifiers": list(sig.get("qualifiers") or []),
                    "status": sig.get("status"),
                    "emittable": sig.get("status") == "active",
                    "layer": sig.get("layer"),
                    "since": sig.get("since"),
                    "unit": sig.get("unit"),
                    "semi_ref": sig.get("semi_ref"),
                    "superseded_by": sig.get("superseded_by"),
                    "declared": True,
                    "atoms": None,
                    "first_at": None,
                    "last_at": None,
                    "classes": None,
                    "sources": [],
                    "edge_state": EDGE_UNMEASURED,
                }
    return edges


def declared_nodes(vocabulary):
    nodes = {}
    for name, entry in vocabulary.ENTITY_TYPES.items():
        nodes[name] = {
            "id": name,
            "type": name,
            "label": _label(entry, name),
            "entity_class": entry.get("class"),
            "keys": list(entry.get("keys") or []),
            "semi_ref": entry.get("semi_ref"),
            "requires_register": vocabulary.requires_register(name),
            "declared": True,
            "atoms_as_subject": None,
            "atoms_as_object": None,
            "registered": None,
            "node_state": EDGE_UNMEASURED,
        }
    return nodes


# ------------------------------------------------------------------- the observed half
#: 🔴 THE CLASS IS NOT COMPUTED IN SQL. THE GROUP KEY IS.
#:
#: The obvious implementation transcribes `ledger_trace.claim_class`'s four-arm ladder
#: into a SQL `CASE`. It was written, measured, and thrown away, for two reasons and the
#: second is the one that matters:
#:
#:   1. It was SLOWER — 285 ms against 152 ms for this spelling, on the same 84,747 atoms
#:      (measured, `assy_manager`, 2026-08-14), because the ladder evaluates a regex per
#:      row on top of the jsonb lookups this one still needs.
#:   2. **It was a SECOND SPELLING of a rule that already has an authority.** Every input
#:      to `claim_class` except the two payload flags is ALREADY a grouping column, so
#:      lifting the flags into the group key lets the census call `claim_class` ITSELF,
#:      once per group, on a claim shim. Nothing re-implements the ladder, nothing can
#:      drift from it, and a site that redeclares `inference_derivations` moves both
#:      halves because there is only one half.
#:
#: The same argument applies to the derivation: `ledger_trace.claim_basis` owns the
#: `#<derivation>` suffix (it uses `rsplit('#', 1)`, which a SQL `split_part(…, 2)` gets
#: WRONG for a version string carrying two separators), so the raw provenance column is
#: grouped and `claim_basis` reads it.
#:
#: Group cardinality stays bounded by the DECLARATION rather than by the atom count:
#: predicates x entity types x translator versions x 2 x 2. Twelve rows on this box, a
#: handful at ten million atoms. Nothing is loaded into Python that is not a group.
CENSUS_SQL = """
SELECT subject_type,
       predicate,
       object_kind,
       CASE WHEN object_kind = 'entity_ref' THEN object_payload->>'type' END,
       source_who,
       source_translator_ver,
       coalesce((object_payload -> %(cls_confirmed_flag)s) = 'true'::jsonb, false),
       coalesce((object_payload -> %(cls_inference_flag)s) = 'true'::jsonb, false),
       count(*),
       min(occurred_at),
       max(occurred_at)
FROM {relation}
{where}
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
"""


class CensusClaim:
    """One census GROUP, shaped like the claim `ledger_trace.claim_class` expects.

    ⚠️ `object_payload` is REBUILT from the two boolean flags rather than carried: the
    real payloads are not in the group key and pulling them would be the whole-table load
    this endpoint refuses. It carries exactly what `claim_class` reads from a payload —
    the declared confirmed flag and the declared inference flag — and nothing else, so
    the shim cannot accidentally answer a question the census did not measure.

    The flags are written as literal `True` only when the SQL comparison said JSON `true`;
    `claim_class` tests `is True`, so an absent flag and a flag holding `1` both land on
    the same answer here as they do there.
    """

    __slots__ = ("predicate", "source_who", "source_translator_ver", "object_payload")

    def __init__(self, predicate, source_who, translator_ver, confirmed, inferred,
                 config):
        self.predicate = predicate
        self.source_who = source_who
        self.source_translator_ver = translator_ver
        payload = {}
        if confirmed:
            payload[config["confirmed_payload_flag"]] = True
        if inferred:
            payload[config["inference_payload_flag"]] = True
        self.object_payload = payload


def census(connection, config, window, relation=LEDGER_RELATION):
    """One pass over the ledger. Returns `(rows, elapsed_ms)`."""
    params = {"cls_confirmed_flag": config["confirmed_payload_flag"],
              "cls_inference_flag": config["inference_payload_flag"]}
    where = ""
    if window.start is not None:
        params["win_from"] = window.start
        where = "WHERE occurred_at >= %(win_from)s"
        if window.end is not None:
            params["win_to"] = window.end
            where += " AND occurred_at < %(win_to)s"
    sql = CENSUS_SQL.format(relation=relation, where=where)
    started = time.time()
    rows = _fetch(connection, sql, params)
    return rows, int((time.time() - started) * 1000)


def _ledger_bytes(connection, relation=LEDGER_RELATION):
    """On-disk size, summed over the partitions. A filesystem stat per partition, never a
    count. Returns `(bytes, partition_count)`; `(None, 0)` when the relation is absent."""
    rows = _fetch(connection, """
        SELECT coalesce(sum(pg_relation_size(c.oid)), 0), count(*)
        FROM pg_class parent
        JOIN pg_inherits i ON i.inhparent = parent.oid
        JOIN pg_class c ON c.oid = i.inhrelid
        WHERE parent.oid = to_regclass(%(rel)s)
    """, {"rel": relation})
    if not rows:
        return None, 0
    return int(rows[0][0] or 0), int(rows[0][1] or 0)


# --------------------------------------------------------------------------- the merge
def _merge(nodes, edges, rows, zone, config):
    """Fold the census into the declared skeleton. Returns the drift lists.

    Merging rather than choosing is the entire design: a shape that is only declared and
    a shape that is only observed are BOTH answers, and each needs the other's absence to
    be visible.

    🔴 The resolution class and the derivation are asked of `ledger_trace` — `claim_class`
    and `claim_basis`, the same two functions the trace screen resolves hops with. See
    `CENSUS_SQL`'s note: this is the reason the SQL groups rather than classifies.
    """
    undeclared_edges, undeclared_nodes = [], []
    for (subject_type, predicate, object_kind, object_type, source_who,
         translator_ver, confirmed_flag, inferred_flag,
         atoms, first_at, last_at) in rows:
        atoms = int(atoms)
        claim = CensusClaim(predicate, source_who, translator_ver,
                            confirmed_flag, inferred_flag, config)
        klass = ledger_trace.CLASS_NAMES[ledger_trace.claim_class(claim, config)]
        derivation = ledger_trace.claim_basis(claim)
        eid = edge_id(subject_type, predicate, object_kind, object_type)
        edge = edges.get(eid)
        if edge is None:
            # 🔴 DRIFT, and it is SHOWN rather than dropped. The gate should make this
            # impossible; if it ever happens, an operator finding out from a screen is
            # the difference between a five-minute fix and a silent ontology fork.
            edge = {
                "id": eid, "source": subject_type, "target": object_type,
                "subject_type": subject_type, "predicate": predicate,
                "predicate_label": predicate,
                "object_kind": object_kind,
                "object_kind_label": (OBJECT_KIND_NONE_LABEL if object_kind is None
                                      else OBJECT_KIND_LABELS.get(object_kind,
                                                                  object_kind)),
                "object_type": object_type, "object_fields": [], "qualifiers": [],
                "status": None, "emittable": False, "layer": None, "since": None,
                "unit": None, "semi_ref": None, "superseded_by": None,
                "declared": False, "atoms": 0, "first_at": None, "last_at": None,
                "classes": _empty_classes(), "sources": [],
                "edge_state": EDGE_UNDECLARED,
            }
            edges[eid] = edge
            undeclared_edges.append(eid)
        if edge["classes"] is None:
            edge["classes"] = _empty_classes()
            edge["atoms"] = 0
        edge["atoms"] += atoms
        edge["classes"][klass] = edge["classes"].get(klass, 0) + atoms
        first = ledger_trace._iso(first_at, zone)
        last = ledger_trace._iso(last_at, zone)
        if edge["first_at"] is None or (first and first < edge["first_at"]):
            edge["first_at"] = first
        if edge["last_at"] is None or (last and last > edge["last_at"]):
            edge["last_at"] = last

        bucket = None
        for candidate in edge["sources"]:
            if (candidate["source_who"] == source_who
                    and candidate["derivation"] == derivation):
                bucket = candidate
                break
        if bucket is None:
            bucket = {"source_who": source_who, "derivation": derivation,
                      "atoms": 0, "classes": _empty_classes()}
            edge["sources"].append(bucket)
        bucket["atoms"] += atoms
        bucket["classes"][klass] = bucket["classes"].get(klass, 0) + atoms

        for name in (subject_type, object_type):
            if name and name not in nodes:
                nodes[name] = {
                    "id": name, "type": name, "label": name, "entity_class": None,
                    "keys": [], "semi_ref": None, "requires_register": None,
                    "declared": False, "atoms_as_subject": 0, "atoms_as_object": 0,
                    "registered": None, "node_state": EDGE_UNDECLARED,
                }
                undeclared_nodes.append(name)
    return undeclared_edges, undeclared_nodes


def _settle(nodes, edges, measured):
    """Assign `edge_state` / `node_state` and roll the edge counts up onto the nodes.

    `measured` is False when the relation is absent — every count stays `null` and every
    state is `unmeasured`. That is the one branch where a 0 would be a lie.
    """
    for edge in edges.values():
        if not measured:
            edge["edge_state"] = EDGE_UNMEASURED
            continue
        if edge["classes"] is None:
            edge["classes"] = _empty_classes()
            edge["atoms"] = 0
        if not edge["declared"]:
            edge["edge_state"] = EDGE_UNDECLARED
        elif edge["atoms"]:
            edge["edge_state"] = EDGE_FLOWING
        else:
            edge["edge_state"] = EDGE_DECLARED_ONLY
        edge["sources"].sort(key=lambda s: (-s["atoms"], s["source_who"] or ""))

    if not measured:
        return
    for node in nodes.values():
        node["atoms_as_subject"] = 0
        node["atoms_as_object"] = 0
        node["registered"] = None
    for edge in edges.values():
        subject = nodes.get(edge["subject_type"])
        if subject is not None:
            subject["atoms_as_subject"] += edge["atoms"] or 0
            # 🔴 THE REGISTRATION EDGE IS IDENTIFIED BY ITS SHAPE, NOT BY ITS NAME.
            # `if edge["predicate"] == "register"` was written here first and
            # `test_the_graph_follows_a_swapped_vocabulary`'s sibling caught it: under a
            # vocabulary whose registration word is spelled differently the count silently
            # stayed `null`. The vocabulary's own rule is that the registration predicate
            # is the one whose object is ∅ — `vocabulary`'s module docstring states it and
            # the DDL's `ck_ledger_register_has_no_object` enforces it for that predicate
            # ALONE — so an objectless edge IS the existence claim, whatever it is called.
            #
            # The count is the number of DISTINCT entities of this type the ledger knows,
            # which is the one number an operator reads a node by. Composed types have no
            # registration by design (§5 rule 3) and keep `null` rather than 0.
            if edge["object_kind"] is None and subject.get("requires_register"):
                subject["registered"] = (subject["registered"] or 0) + (edge["atoms"] or 0)
        target = nodes.get(edge["object_type"]) if edge["object_type"] else None
        if target is not None:
            target["atoms_as_object"] += edge["atoms"] or 0
    for node in nodes.values():
        if not node["declared"]:
            node["node_state"] = EDGE_UNDECLARED
        elif node["atoms_as_subject"] or node["atoms_as_object"]:
            node["node_state"] = EDGE_FLOWING
        else:
            node["node_state"] = EDGE_DECLARED_ONLY


# ------------------------------------------------------------------ vocabulary panel
def _vocabulary_panel(vocabulary, edges):
    """Panel 2 — one row per predicate, with the EDGE IDS it owns.

    The `edge_ids` linkage is the point: a client showing this panel beside the graph can
    highlight without matching on names, and「선언은 있는데 소비자가 없다」is visible as a
    predicate whose every edge is `declared_only`.
    """
    rows = []
    for predicate, sig in vocabulary.PREDICATES.items():
        mine = [e for e in edges.values() if e["predicate"] == predicate]
        atoms = None
        classes = None
        if any(e["atoms"] is not None for e in mine):
            atoms = sum(e["atoms"] or 0 for e in mine)
            classes = _empty_classes()
            for e in mine:
                for name, n in (e["classes"] or {}).items():
                    classes[name] = classes.get(name, 0) + n
        declared_object = sig.get("object") or {}
        rows.append({
            "predicate": predicate,
            "label": _label(sig, predicate),
            "layer": sig.get("layer"),
            "status": sig.get("status"),
            "emittable": sig.get("status") == "active",
            "since": sig.get("since"),
            "subject_types": list(sig.get("subject") or []),
            "object_kind": declared_object.get("kind") if sig.get("object") else None,
            "object_types": list(declared_object.get("types") or []),
            "object_fields": list(declared_object.get("required") or []),
            "qualifiers": list(sig.get("qualifiers") or []),
            "unit": sig.get("unit"),
            "semi_ref": sig.get("semi_ref"),
            "superseded_by": sig.get("superseded_by"),
            "atoms": atoms,
            "classes": classes,
            "edge_ids": sorted(e["id"] for e in mine),
        })
    rows.sort(key=lambda r: (-(r["atoms"] or 0), r["predicate"]))
    return {
        "predicates": rows,
        "object_kinds": ([{"kind": None, "label": OBJECT_KIND_NONE_LABEL}]
                         + [{"kind": k, "label": OBJECT_KIND_LABELS.get(k, k)}
                            for k in sorted(vocabulary.OBJECT_KINDS)]),
        "classes": [{"name": name, "rank": rank,
                     "label": CLASS_LABELS.get(name, name)}
                    for rank, name in sorted(ledger_trace.CLASS_NAMES.items())],
        "entity_types": [{"type": n, "label": _label(e, n), "class": e.get("class"),
                          "keys": list(e.get("keys") or []),
                          "semi_ref": e.get("semi_ref")}
                         for n, e in vocabulary.ENTITY_TYPES.items()],
        "projection_only_words": sorted(vocabulary.PROJECTION_ONLY_WORDS),
    }


# ------------------------------------------------------- the mechanism layer (M4)
#: Where a mechanism-graph declaration would live, under this project's standing config
#: convention (`server/config/<name>.json`, operator-owned and gitignored, with a
#: committed `.json.sample` twin — the shape `siblings_axes.json` already uses).
MECHANISM_CONFIG_FILENAME = "mechanism_models.json"

#: The design section that proposes the shape. SERVED in the response so an operator who
#: sees「없음」can go read what it would be, without anybody having to remember.
MECHANISM_SPEC_REF = "docs/architecture/PHYSICS_ONTOLOGY_SETUP.md §4"

MECH_STATE_ABSENT = "absent"        # no declaration a process can open
MECH_STATE_DECLARED = "declared"    # a declaration loads
MECH_REASON_NO_FILE = "no_declaration_file"
MECH_REASON_UNREADABLE = "declaration_unreadable"
MECH_REASON_NO_MODEL_ENTITY = "no_model_entity_type"

#: The three edge directions §4 declares, and what each says. `u` is NON-MONOTONE and is
#: emphatically not "unknown" — a screen that renders it as a question mark would lose the
#: one thing the modeller actually asserted.
MECHANISM_DIRECTION_LABELS = {"+": "증가", "-": "감소", "u": "비단조"}


def mechanism_layer(vocabulary):
    """The M4 mechanism graph as a SECOND LAYER of the same picture. Read-only.

    🔴 MEASURED, 2026-08-14: **it does not exist as anything a process can open.** §4 of
    `PHYSICS_ONTOLOGY_SETUP.md` carries a complete proposed shape inside a markdown code
    fence, the doc's own status table marks it 🟡 제안, and the repository holds no config
    file, no Python dict, no loader, no route and no `Model` entity type. Consumers: zero
    — and「선언만 있고 소비자 0」is generous, because the declaration is prose.

    So this function DOES NOT INVENT ONE. It opens the seam where a declaration belongs,
    reports `state: "absent"` with the reason and the doc reference in structured fields,
    and renders whatever it finds the day somebody lands the file — same node and edge
    field names as the ledger layer, so the client keeps one renderer.

    🔴 `ledger_link` is the answer to「이 축이 원장의 어느 엣지에 닿는가」, and it is
    computed rather than asserted: a mechanism node reaches the ledger through a `Model`
    entity type, the vocabulary declares no such type, so the answer is that there is
    nowhere for the linkage to attach. That is derived from the declaration in front of
    it, which means it stops being true by itself on the day a `Model` type is declared.
    """
    model_entity = next((name for name in vocabulary.ENTITY_TYPES
                         if name.lower() == "model"), None)
    ledger_link = {
        "entity_type": model_entity,
        "reason": None if model_entity else MECH_REASON_NO_MODEL_ENTITY,
        "message": (None if model_entity else
                    "어휘에 Model 개체 유형이 없다 — 기전 노드가 원장 엣지에 붙을 자리가 "
                    "아직 없음"),
    }
    origin, path = _origin(MECHANISM_CONFIG_FILENAME)
    layer = {
        "state": MECH_STATE_ABSENT,
        "declared": False,
        "config": MECHANISM_CONFIG_FILENAME,
        "origin": origin,
        "path": path,
        "spec_ref": MECHANISM_SPEC_REF,
        "models": [],
        "nodes": [],
        "edges": [],
        "directions": [{"dir": d, "label": lbl}
                       for d, lbl in MECHANISM_DIRECTION_LABELS.items()],
        "ledger_link": ledger_link,
        "reason": MECH_REASON_NO_FILE,
        "message": ("기전 그래프(M4) 선언 파일 없음 — %s의 제안만 있고 코드가 읽는 "
                    "선언은 없다. 소비자 0." % MECHANISM_SPEC_REF),
    }
    if origin == ORIGIN_ABSENT:
        return layer

    import json
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if not isinstance(raw, dict):
            raise ValueError("최상위가 객체가 아님")
    except Exception as exc:
        layer["reason"] = MECH_REASON_UNREADABLE
        layer["message"] = "기전 그래프 선언을 읽을 수 없음: %s" % exc
        return layer

    nodes, edges, models = {}, [], []
    for model_name, model in raw.items():
        if model_name.startswith("__") or not isinstance(model, dict):
            continue
        declared_nodes_ = [str(n) for n in (model.get("nodes") or [])]
        model_edges = []
        for spec in model.get("edges") or []:
            if not isinstance(spec, dict):
                continue
            head, tail = str(spec.get("from") or ""), str(spec.get("to") or "")
            direction = spec.get("dir")
            eid = "%s|%s->%s" % (model_name, head, tail)
            model_edges.append(eid)
            edges.append({
                "id": eid,
                "model": model_name,
                "source": head,
                "target": tail,
                "dir": direction,
                "dir_label": MECHANISM_DIRECTION_LABELS.get(direction, str(direction)),
                # `form` is null until an equation is known and §4's point is that the
                # direction alone is enough to walk — so `has_form` is served rather than
                # left to a client testing a null.
                "form": spec.get("form"),
                "has_form": spec.get("form") is not None,
                "atoms": None,
                "edge_state": EDGE_DECLARED_UNCONSUMED,
            })
            for endpoint in (head, tail):
                if endpoint and endpoint not in nodes:
                    nodes[endpoint] = {
                        "id": endpoint, "label": endpoint, "model": model_name,
                        "atoms": None, "node_state": EDGE_DECLARED_UNCONSUMED,
                    }
        for name in declared_nodes_:
            if name not in nodes:
                # Declared as a node and touched by no edge — an isolated quantity, which
                # is a fact about the model and is kept rather than tidied away.
                nodes[name] = {"id": name, "label": name, "model": model_name,
                               "atoms": None,
                               "node_state": EDGE_DECLARED_UNCONSUMED}
        models.append({
            "model": model_name,
            "version": model.get("version"),
            "nodes": declared_nodes_,
            "edge_ids": model_edges,
            "validity": model.get("validity"),
        })

    layer.update({
        "state": MECH_STATE_DECLARED,
        "declared": True,
        "models": models,
        "nodes": sorted(nodes.values(), key=lambda n: n["id"]),
        "edges": edges,
        "reason": None,
        "message": None,
    })
    return layer


# ----------------------------------------------------------------- declaration map
def _origin(filename):
    """`(origin, path)` under this project's live/sample convention, asked the way every
    loader in the ledger asks it: the operator's file first, the shipped sample second."""
    try:
        import paths
        base = os.path.join(paths.CONFIG_DIR, filename)
    except Exception:                                              # pragma: no cover
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config",
                            filename)
    if os.path.exists(base):
        return ORIGIN_LIVE, base
    if os.path.exists(base + ".sample"):
        return ORIGIN_SAMPLE, base + ".sample"
    return ORIGIN_ABSENT, base


def _edges_of_source(edges, source_who):
    return sorted(e["id"] for e in edges.values()
                  if any(s["source_who"] == source_who for s in e["sources"]))


def _translator_declarations(edges, cursors, seen_sources):
    """Panel 4a — `ledger_config.json`: which source becomes which atoms.

    🔴 The linkage is DERIVED from `source_who` on the atoms, not guessed by name
    similarity. A declared source that has written nothing gets `edge_ids: []` and an
    UNDECLARED source that has written 83,838 atoms gets an entry of its own — on this box
    both cases are real, and neither is visible anywhere else.
    """
    items = []
    origin, path = _origin("ledger_config.json")
    declared_names = set()
    try:
        from ledger import config as ledger_config
        cfg = ledger_config.load()
        sources = cfg.get("sources") or {}
    except Exception as exc:
        logger.warning("structure: translator declarations unreadable: %s", exc)
        return [{
            "id": "ledger_config", "group": "translator",
            "config": "ledger_config.json", "origin": origin, "path": path,
            "declares": "소스 → 원장 번역",
            "name": None, "label": "ledger_config.json",
            "readable": False, "error": str(exc),
            "detail": {}, "node_ids": [], "edge_ids": [], "atoms": None,
            "link": "source_who",
        }]

    for name, source in sources.items():
        declared_names.add(name)
        vocab = {k: v for k, v in (source.get("vocabulary") or {}).items()
                 if not k.startswith("__")}
        try:
            derivations = sorted(ledger_config.declared_derivations(cfg, name))
        except Exception:                                          # pragma: no cover
            derivations = []
        ids = _edges_of_source(edges, name)
        seen = sorted({s["derivation"] for e in edges.values() for s in e["sources"]
                       if s["source_who"] == name and s["derivation"]})
        items.append({
            "id": "ledger_config:%s" % name, "group": "translator",
            "config": "ledger_config.json", "origin": origin, "path": path,
            "declares": "소스 → 원장 번역",
            "name": name, "label": name, "readable": True,
            "detail": {
                "occurred_at_column": source.get("occurred_at_column"),
                "occurred_at_timezone": source.get("occurred_at_timezone"),
                "subject_types": list(source.get("subject_types") or []),
                "event_types": sorted(vocab),
                "strategies": {k: {"lineage": v.get("lineage", "none"),
                                   "slot_pairing": v.get("slot_pairing", "none")}
                               for k, v in vocab.items()},
                "derivations_declared": derivations,
                "derivations_seen": seen,
                "translator_ver": ledger_config.translator_version(cfg, name),
            },
            "node_ids": list(source.get("subject_types") or []),
            "edge_ids": ids,
            "atoms": sum(sum(s["atoms"] for s in edges[i]["sources"]
                             if s["source_who"] == name) for i in ids) if ids else 0,
            "link": "source_who",
        })

    # Sources the LEDGER knows about that the declaration does not. Two registries carry
    # them and they are different registries: `source_who` is stamped on each atom, and
    # the cursor table is the writer's own row. Both are reported, because a writer that
    # has a cursor and no atoms is a different fact from atoms with no cursor.
    for source_who in sorted(seen_sources - declared_names):
        ids = _edges_of_source(edges, source_who)
        items.append({
            "id": "undeclared_source:%s" % source_who, "group": "translator",
            "config": "ledger_config.json", "origin": origin, "path": path,
            "declares": "소스 → 원장 번역",
            "name": source_who, "label": source_who, "readable": True,
            "declared": False,
            "detail": {"note": "원장에 원자가 있으나 ledger_config.json에 선언 없음"},
            "node_ids": sorted({edges[i]["subject_type"] for i in ids}),
            "edge_ids": ids,
            "atoms": sum(sum(s["atoms"] for s in edges[i]["sources"]
                             if s["source_who"] == source_who) for i in ids),
            "link": "source_who",
        })
    for row in cursors:
        name = row.get("source")
        if name in declared_names or name in seen_sources:
            continue
        items.append({
            "id": "cursor_only:%s" % name, "group": "translator",
            "config": "ledger_translator_cursor", "origin": ORIGIN_ABSENT, "path": None,
            "declares": "번역기 커서", "name": name, "label": name, "readable": True,
            "declared": False,
            "detail": {"note": "커서 행은 있으나 선언도 원자도 없음", "cursor": row},
            "node_ids": [], "edge_ids": [], "atoms": 0, "link": "cursor",
        })

    by_source = {row.get("source"): row for row in cursors}
    for item in items:
        item["cursor"] = by_source.get(item["name"])
    return items


def _axis_declarations(edges):
    """Panel 4b — `siblings_axes.json`: the factor axes.

    🔴 THEIR `edge_ids` ARE EMPTY, AND THAT IS THE FINDING. Every axis attributes a
    population through a SOURCE TABLE (`bonding_log`, `inspection_run`) that the ledger
    does not translate — no predicate carries a bonding equipment or a scan recipe. So
    `link: "source_table"` and `link_reason` say so in structured fields rather than
    leaving a client to wonder whether the linkage failed or never existed.
    """
    origin, path = _origin(ledger_siblings.AXES_CONFIG_FILENAME)
    try:
        axes_cfg = ledger_siblings.load_axes_config()
    except Exception as exc:
        return [{
            "id": "siblings_axes", "group": "axis",
            "config": ledger_siblings.AXES_CONFIG_FILENAME,
            "origin": origin, "path": path, "declares": "요인 축",
            "name": None, "label": ledger_siblings.AXES_CONFIG_FILENAME,
            "readable": False, "error": str(exc), "detail": {},
            "node_ids": [], "edge_ids": [], "link": "source_table",
            "link_reason": "declaration_unreadable",
        }]

    items = [{
        "id": "siblings_axes:geometry", "group": "axis",
        "config": ledger_siblings.AXES_CONFIG_FILENAME, "origin": origin, "path": path,
        "declares": "모집단 기하 (분모의 단위)",
        "name": "geometry", "label": axes_cfg.geometry.unit_label, "readable": True,
        "detail": {
            "unit": axes_cfg.geometry.unit,
            "unit_columns": list(axes_cfg.geometry.unit_columns),
            "run_relation": finding_kinds.RUN_TABLE,
            "universe_relation": axes_cfg.geometry.universe_relation,
        },
        "node_ids": [], "edge_ids": [], "link": "source_table",
        "link_reason": "not_translated_to_ledger",
    }]
    for source in axes_cfg.attribution:
        for axis in source.axes:
            items.append({
                "id": "siblings_axes:%s" % axis.name, "group": "axis",
                "config": ledger_siblings.AXES_CONFIG_FILENAME,
                "origin": origin, "path": path, "declares": "요인 축",
                "name": axis.name, "label": axis.label, "readable": True,
                "detail": {"about": axis.about, "relation": axis.relation,
                           "column": axis.column,
                           "source": "%s.%s" % (axis.relation, axis.column),
                           "narrowed_by": source.filter_values_from},
                "node_ids": [], "edge_ids": [], "link": "source_table",
                "link_reason": "not_translated_to_ledger",
            })
    return items


def _resolver_declarations(config, edges):
    """Panel 4c — `ledger_resolver.json`: the class table, linked to the edges it MOVES.

    Not a decoration: `slot_preserving` is a declared convention, and the reason 127 of
    the `Lot -slot_map-> Lot` atoms resolve at class 3 while 26 resolve at class 2. The
    operator can see which declaration did that only if the linkage is computed, so it is
    — from the derivations the census actually observed, not from a table of guesses.
    """
    origin, path = _origin(ledger_trace.RESOLVER_CONFIG_FILENAME)
    if origin == ORIGIN_ABSENT:
        origin, path = ORIGIN_CODE_DEFAULT, None

    def by_predicate(names):
        return sorted(e["id"] for e in edges.values() if e["predicate"] in set(names))

    def by_derivation(names):
        wanted = set(names)
        return sorted(e["id"] for e in edges.values()
                      if any(s["derivation"] in wanted for s in e["sources"]))

    rules = [
        ("pin_predicates", "핀 (등급 0)", list(config["pin_predicates"]),
         by_predicate(config["pin_predicates"]), "predicate"),
        ("confirmed_predicates", "확정 (등급 1)", list(config["confirmed_predicates"]),
         by_predicate(config["confirmed_predicates"]), "predicate"),
        ("confirmed_sources", "확정 발화자 (등급 1)", list(config["confirmed_sources"]),
         sorted(e["id"] for e in edges.values()
                if any(s["source_who"] in set(config["confirmed_sources"])
                       for s in e["sources"])), "source_who"),
        ("inference_derivations", "추론 유도 (등급 3)",
         list(config["inference_derivations"]),
         by_derivation(config["inference_derivations"]), "derivation"),
        ("inference_sources", "추론 발화자 (등급 3)", list(config["inference_sources"]),
         sorted(e["id"] for e in edges.values()
                if any(s["source_who"] in set(config["inference_sources"])
                       for s in e["sources"])), "source_who"),
        ("inference_payload_flag", "추론 페이로드 플래그 (등급 3)",
         [config["inference_payload_flag"]], [], "payload_flag"),
        ("confirmed_payload_flag", "확정 페이로드 플래그 (등급 1)",
         [config["confirmed_payload_flag"]], [], "payload_flag"),
    ]
    return [{
        "id": "ledger_resolver:%s" % key, "group": "resolver",
        "config": ledger_trace.RESOLVER_CONFIG_FILENAME, "origin": origin, "path": path,
        "declares": "해소 등급 표", "name": key, "label": label, "readable": True,
        "detail": {"values": values,
                   # A payload flag cannot be linked to an edge without reading every
                   # atom's payload, which is the whole-table scan this endpoint refuses.
                   # Saying so is better than an empty list that looks like "no matches".
                   "matched_on": matched_on},
        "node_ids": [], "edge_ids": ids,
        "link": matched_on,
        "link_reason": (None if matched_on != "payload_flag"
                        else "per_atom_payload_not_censused"),
    } for key, label, values, ids, matched_on in rules]


def _mechanism_declarations(mechanism):
    """Panel 4e — the mechanism graph, as a DECLARATION with a consumer count.

    One row even when nothing is declared, because「선언 자체가 없다」is the answer the
    lead PM asked this layer to make visible, and a row that disappears when it is absent
    can never say it.
    """
    if not mechanism["declared"]:
        return [{
            "id": "mechanism_models", "group": "mechanism",
            "config": mechanism["config"], "origin": mechanism["origin"],
            "path": mechanism["path"], "declares": "기전 그래프 (인과 모델)",
            "name": None, "label": "기전 그래프 (M4)", "readable": False,
            "declared": False,
            "detail": {"reason": mechanism["reason"],
                       "message": mechanism["message"],
                       "spec_ref": mechanism["spec_ref"]},
            "node_ids": [], "edge_ids": [],
            "link": "model_entity",
            "link_reason": mechanism["ledger_link"]["reason"],
        }]
    return [{
        "id": "mechanism_models:%s" % model["model"], "group": "mechanism",
        "config": mechanism["config"], "origin": mechanism["origin"],
        "path": mechanism["path"], "declares": "기전 그래프 (인과 모델)",
        "name": model["model"], "label": model["model"], "readable": True,
        "declared": True,
        "detail": {"version": model["version"], "nodes": model["nodes"],
                   "validity": model["validity"],
                   "spec_ref": mechanism["spec_ref"]},
        "node_ids": list(model["nodes"]),
        # 🔴 The mechanism model's own edges, NOT ledger edges. `link_reason` says why the
        # ledger column is empty, so a client never has to guess whether the linkage
        # failed or never existed.
        "edge_ids": list(model["edge_ids"]),
        "link": "model_entity",
        "link_reason": mechanism["ledger_link"]["reason"],
    } for model in mechanism["models"]]


def _kind_declarations(kinds_panel):
    """Panel 4d — `finding_kinds`: the kinds, and their (absent) ledger edges."""
    origin, path = _origin(finding_kinds.CONFIG_FILENAME)
    if origin == ORIGIN_ABSENT:
        origin, path = ORIGIN_CODE_DEFAULT, None
    return [{
        "id": "finding_kinds:%s" % row["kind"], "group": "kind",
        "config": finding_kinds.CONFIG_FILENAME, "origin": origin, "path": path,
        "declares": "불량 종류 (분모 정의)",
        "name": row["kind"], "label": row["label"], "readable": True,
        "detail": {"observed_by": row["observed_by"],
                   "has_denominator": row["has_denominator"],
                   "observation_table": row["observation_table"],
                   "classes": row["classes"],
                   "atoms": row["atoms"], "runs": row["runs"]},
        "node_ids": [], "edge_ids": row["ledger_edge_ids"],
        "link": "predicate",
        "link_reason": (None if row["ledger_edge_ids"] else "no_predicate_declared"),
    } for row in kinds_panel.get("kinds") or []]


# --------------------------------------------------------------------------- the answer
def structure(connection, window=None, relation=LEDGER_RELATION,
              cursor_relation=LEDGER_CURSOR_RELATION, config=None):
    """The whole type-level picture, in one read-only call.

    Never raises for an absent or empty ledger — those are two of the three answers
    (`state`), exactly as they are for `GET /coverage` and `GET /kinds`. The declared half
    of the graph is served in every one of them, because a box with no ledger at all still
    has an ontology and that is precisely what somebody looking at a blank screen needs.
    """
    cfg = config or ledger_trace.load_resolver_config()
    zone = ledger_trace.resolve_display_zone(cfg)
    vocabulary = _vocabulary()

    nodes = declared_nodes(vocabulary)
    edges = declared_edges(vocabulary)

    exists = relation_exists(connection, relation)
    size_bytes, partitions = (None, 0)
    census_ms = None
    rows = []
    window_obj = ledger_siblings.parse_window(window)
    forced = False
    forced_reason = None

    if exists:
        size_bytes, partitions = _ledger_bytes(connection, relation)
        if (not window_obj.declared and size_bytes is not None
                and size_bytes > FULL_CENSUS_MAX_BYTES):
            # 🔴 The counts narrow; the STRUCTURE does not. Every declared edge is still
            # on the screen, at `atoms: 0` — see the module docstring.
            window_obj = ledger_siblings.parse_window(LARGE_LEDGER_WINDOW)
            forced = True
            forced_reason = REASON_LEDGER_TOO_LARGE
            logger.info("structure: %s is %s bytes; census forced to %s",
                        relation, size_bytes, LARGE_LEDGER_WINDOW)
        rows, census_ms = census(connection, cfg, window_obj, relation=relation)

    undeclared_edge_ids, undeclared_node_ids = _merge(nodes, edges, rows, zone, cfg)
    _settle(nodes, edges, measured=exists)

    seen_sources = {s["source_who"] for e in edges.values() for s in e["sources"]
                    if s["source_who"]}
    atoms_counted = sum(int(r[8]) for r in rows) if exists else None

    if not exists:
        state = STATE_ABSENT
    elif atoms_counted:
        state = STATE_READY
    else:
        state = STATE_EMPTY

    kinds_panel = _kinds_panel(connection, edges)
    cursors = _cursors(connection, cursor_relation, zone)

    mechanism = mechanism_layer(vocabulary)

    declarations = []
    declarations.extend(_translator_declarations(edges, cursors, seen_sources))
    declarations.extend(_axis_declarations(edges))
    declarations.extend(_resolver_declarations(cfg, edges))
    declarations.extend(_kind_declarations(kinds_panel))
    declarations.extend(_mechanism_declarations(mechanism))

    node_list = sorted(nodes.values(),
                       key=lambda n: (-(n["atoms_as_subject"] or 0), n["id"]))
    edge_list = sorted(edges.values(), key=lambda e: (-(e["atoms"] or 0), e["id"]))

    # 🔴 TWO LAYERS OF ONE PICTURE, and the client enumerates them rather than knowing
    # their names. The ledger layer is what data flows through; the mechanism layer is
    # what somebody DECLARED flows through. Putting them side by side is what makes an
    # axis that is declared and read by nobody visible at all — see `mechanism_layer`.
    layers = [
        {"id": "ledger", "label": "원장 (유형 수준)", "state": state,
         "nodes": len(node_list), "edges": len(edge_list),
         "atoms": atoms_counted, "reason": None, "message": None,
         "spec_ref": None},
        {"id": "mechanism", "label": "기전 그래프 (M4)", "state": mechanism["state"],
         "nodes": len(mechanism["nodes"]), "edges": len(mechanism["edges"]),
         "atoms": None, "reason": mechanism["reason"],
         "message": mechanism["message"], "spec_ref": mechanism["spec_ref"]},
    ]

    return {
        "generated_at": ledger_trace._iso(datetime.now(timezone.utc), zone),
        "state": state,
        "relation": relation,
        "window": dict(window_obj.as_dict(), forced=forced,
                       forced_reason=forced_reason),
        "cost": {
            "census_ms": census_ms,
            "atoms_counted": atoms_counted,
            "groups": len(rows),
            "exact": bool(exists),
            "relation_bytes": size_bytes,
            "partitions": partitions,
            "full_census_max_bytes": FULL_CENSUS_MAX_BYTES,
            "large_ledger_window": LARGE_LEDGER_WINDOW,
        },
        "graph": {"nodes": node_list, "edges": edge_list,
                  "layers": layers, "mechanism": mechanism},
        "vocabulary": _vocabulary_panel(vocabulary, edges),
        "kinds": kinds_panel,
        "declarations": declarations,
        "cursors": cursors,
        "drift": {
            "undeclared_edge_ids": sorted(undeclared_edge_ids),
            "undeclared_node_ids": sorted(undeclared_node_ids),
            "undeclared_sources": sorted(
                seen_sources - _declared_source_names()),
        },
    }


def _declared_source_names():
    try:
        from ledger import config as ledger_config
        return set((ledger_config.load().get("sources") or {}))
    except Exception:
        return set()


def _kinds_panel(connection, edges):
    """Panel 3 — `GET /api/ledger/kinds`' body, REUSED, plus the ledger linkage.

    🔴 Reused rather than re-derived. The kind registry is another lane's SSOT and
    `ledger_kinds.catalog` already answers everything about it; a second catalogue here
    would be the exact drift its own docstring exists to prevent.

    🔴 THIS PANEL ADDS ONE FIELD (`ledger_edge_ids`) AND OVERWRITES NONE.
    ------------------------------------------------------------------------
    It used to overwrite `in_ledger` too, and that is how this endpoint came to disagree
    with `GET /api/ledger/kinds` about the same fact. MEASURED 2026-08-14, one live call
    each, `assy_manager`: `/kinds` answered `in_ledger: true` for both `void` and `delam`
    (91,756 + 10,421 atoms, `ledger_state: "flowing"`) while THIS panel answered
    `in_ledger: false` — and the same response's own `graph.edges` carried
    `Wafer|observed|value` at 102,177 atoms, `edge_state: "flowing"`, sourced from
    `void_obs` and `delam_obs`. One response contradicted itself and the other endpoint.

    The cause was a predicate that could never match: the test was
    `row["kind"] in edge["object_fields"]`, but `object_fields` holds the object's
    REQUIRED FIELD NAMES (`["finding_kind", "method", "run_uid"]`) and `row["kind"]` holds
    a VALUE (`"void"`). A name is compared against a value, so it was false for every kind
    on every box, forever — including the boxes where the answer was `false` anyway, which
    is why nothing noticed until the observations landed.

    🔴 `in_ledger` HAS AN AUTHORITY AND IT IS NOT HERE. `ledger_kinds.catalog` answers it
    from the TRANSLATOR DECLARATION (ruling R-2026-08-14-D: a declaration fact, answerable
    on a box with no ledger table at all), and it serves `ledger_state` / `ledger_atoms`
    for the MEASURED half beside it. This panel's job is the third question — WHICH EDGES —
    and a second spelling of the first question is what produced the disagreement.

    `ledger_edge_ids` is therefore derived from the same declaration `in_ledger` is, so the
    two can never part company: the edges carrying the kind's declared `ledger_predicate`.
    Not from the census's `source_who`, deliberately — that would make the list go empty
    for a declared kind whose backfill has not run yet, and `_kind_declarations` would then
    report `link_reason: "no_predicate_declared"` about a predicate that IS declared. The
    count is already the measured half's job.
    """
    try:
        panel = ledger_kinds.catalog(connection)
    except Exception as exc:
        logger.warning("structure: kind catalogue unreadable: %s", exc)
        return {"state": STATE_ABSENT, "default": "", "kinds": [],
                "readable": False, "error": str(exc)}
    # The edges this kind's declared predicate owns — declared ones AND any undeclared one
    # the census turned up under the same predicate, so drift is linked rather than hidden.
    # An undeclared kind has no `ledger_predicate`, and `None` is guarded explicitly rather
    # than left to compare unequal against every edge: a null predicate must never link.
    for row in panel.get("kinds") or []:
        predicate = row.get("ledger_predicate")
        row["ledger_edge_ids"] = ([] if not predicate else
                                  sorted(e["id"] for e in edges.values()
                                         if e["predicate"] == predicate))
    panel["readable"] = True
    return panel


def _cursors(connection, cursor_relation, zone):
    """The translator cursor table. O(sources) — one row per translator, forever."""
    if not relation_exists(connection, cursor_relation):
        return []
    rows = _fetch(connection, """
        SELECT source, translator_ver, molecules_done, atoms_written, atoms_deduped,
               molecules_refused, incomplete_molecules, updated_at
        FROM {} ORDER BY source
    """.format(cursor_relation))
    return [{
        "source": r[0], "translator_ver": r[1], "molecules_done": int(r[2] or 0),
        "atoms_written": int(r[3] or 0), "atoms_deduped": int(r[4] or 0),
        "molecules_refused": int(r[5] or 0),
        "incomplete_molecules": int(r[6] or 0),
        "updated_at": ledger_trace._iso(r[7], zone),
    } for r in rows]
