"""The closed vocabulary, with a machine-checkable signature per entry.

`CANONICAL_LEDGER_DESIGN.md` §4 splits the language in two and this module holds both,
because the GATE has to check one thing ("is this word declared, and does this atom fit
its declared shape?") and a reader has to find one list.

  * §4.1 **canonical** - the grammar of the record. `register`, `pin`, reserved
    `same_as` / `action:*`. Effectively frozen; changing it is a migration-class event.
  * §4.2 **ontology** - the language of the world. `derived_from`, `slot_map`,
    `has_wafer`, `frame_confirmed`. Grows append-only.

**v0 is SEVEN and the number is a control, not a coincidence** (`LEDGER_SLICE_1_BRIEF`
§5 risk 4: "v0 7개 고정"). A vocabulary that grows quietly is how a closed vocabulary
stops being one, so `PREDICATES` is asserted to be exactly this set by
`test_ledger_l1_unit.py`. Adding an eighth is a ruling, and the test is where the ruling
has to be written down.

WHY THE SIGNATURE IS DATA AND NOT AN `if` LADDER
------------------------------------------------
§4.3 declares that every vocabulary entry carries a signature - which subject types it
accepts, which object kind, which unit. `ROOT_DEFECTS`'s fourth root is "대조 안 함"
(nothing is checked against anything), and the design's answer is precisely that the
signature is mechanically verified. An `if predicate == ...` ladder cannot be verified
against a declaration because it IS the declaration; a table can.

WHY `register` HAS NO OBJECT KIND
----------------------------------
The design says its object is ∅. The physical column enum pinned for this slice is
`value | entity_ref | event_ref`, and ∅ is none of those. Inventing a fourth value would
put a word in the enum that the design does not have, so `register` instead carries
`object_kind IS NULL` and the DDL's CHECK constraint makes that legal for `register`
ALONE. Stated here because it is the one place this implementation had to decide
something the pinned contract did not spell out.

🔴 WALK SEMANTICS ARE PART OF THE DECLARATION (ruling R-2026-08-14-E)
----------------------------------------------------------------------
`traversable` and `direction` say what the LINEAGE WALK may do with a word, and they live
here rather than in `ledger_trace.LINEAGE_PREDICATES` because the tuple over there was a
second list of the vocabulary: a predicate added here could never join the walk without an
edit in a module that does not know the vocabulary exists, and one that MUST NOT join it
had nothing to say so with.

`traversable` has THREE states and the third one is the point:

    True    the walk RECURSES through this edge   — lineage (`derived_from`)
    False   reached and fetched as an ANNOTATION of a lot the walk already got to,
            never passed through — 「도달은 하되 통과 금지」
    None    the walk does not fetch it AT ALL. Scoped requests only.

`None` is not "unset". `observed` carries it deliberately (ruling R-2026-08-14-D addendum
①): a wafer holds tens of thousands of observations, and a walk that dragged them back
with the lot's lineage would die the moment the defect translator succeeded. Observations
are fetched by an explicitly scoped request (kind, period) and never by reaching a lot.

`direction` constrains which way a traversable edge is followed
(`subject_to_object` = child -> parent for `derived_from`). It is `None` for everything
that is not traversed, because a direction on an edge nobody walks is a decoy field.

🔴 `degree_cap` IS NOT DECLARED HERE YET, AND THAT IS DELIBERATE. R-2026-08-14-E asks for
it; the enforcement point is inside `ledger_trace`'s recursive CTE (a per-node
`LEFT JOIN LATERAL … LIMIT`), which is the one query in this system whose plan has already
been measured and argued about, and a cap declared without that change would be a field
nothing reads — the decoy R-2026-08-13-D exists to prevent. It arrives with its
enforcement, in its own round, and「허브에서 정지」reports through the walk's existing
`truncation_reason` rather than through a new response field.
"""
from __future__ import annotations

import json
import os
import re

#: Object kinds, exactly as pinned for slice 1. `None` additionally means ∅ and is
#: legal only for a predicate whose signature declares `object` as `None`.
OBJECT_KINDS = frozenset({"value", "entity_ref", "event_ref"})


#: 🔴 `label_ko` IS PART OF THE DECLARATION, NOT DECORATION.
#:
#: `GET /api/ledger/structure` renders this vocabulary as a picture and the picture's
#: labels are Korean (readability is a function of this project, not a preference). The
#: label therefore has to come from the same place the word does. The alternative - a
#: label map living beside the renderer - is a SECOND list of the vocabulary, and a second
#: list is how a word added here shows up on screen as a bare identifier while every test
#: still passes.
#:
#: The enforcement point (this project's standing rule: a declaration field has one, or it
#: does not exist) is `test_ledger_l1_unit.py::test_every_declared_word_carries_a_label`.
#: A reader that meets an entry without one falls back to the raw name rather than
#: raising - the screen degrades to English, it does not go blank.
#:
#: Entity types (§4.2). `register` is required for ISSUED types and forbidden for
#: COMPOSED ones - `Die` exists by construction (Wafer x product grid) and registering
#: it would mean 160M register atoms for no gain (§5 rule 3).
ENTITY_TYPES = {
    "Lot":       {"class": "issued",   "keys": ["lot"],       "semi_ref": "E90 substrate",
                  "label_ko": "랏"},
    "Wafer":     {"class": "issued",   "keys": ["wafer"],     "semi_ref": "E90 substrate",
                  "label_ko": "웨이퍼"},
    # REJECTED MODEL (superseded by the owner's experiment-plan ruling): a physical base
    # wafer was once split into issued subjects.  The rationale below is retained only to
    # document why that tempting model was implemented and then removed.
    # 🔴 AN AGGREGATION UNIT, AND ITS ROOT KEY IS DECLARED (ruling R-2026-08-15-O).
    # The owner's definition: 「본딩 시 다이별로 조건이 달라서 생기는, 본딩 후 자재에만
    # 성립하는 집계 단위」. Its existence as a separate subject is FORCED - a wafer bonded
    # at two pressures makes "저압으로 붙었다" and "고압으로 붙었다" both true, and under one
    # subject those are competing claims on the same (subject, predicate) that the resolver
    # would settle by killing one. Splitting the subject is what lets both live.
    #
    # The price is that reads split too, and they did so SILENTLY: 42 atoms (MEASURED
    # 2026-08-15 - `observed` 18, `register` 12, `processed_with` 12, over 6 root wafers)
    # were invisible to every wafer-scope query, so the screen read「본딩 조건 차이 없음」
    # and that was false. `rolls_up_to` + `root_key` are what a reader joins on instead of
    # a single `subject_type`.
    #
    # 🔴 DECLARED, NEVER INFERRED FROM KEY CONTAINMENT. `Die`'s keys (wafer, x, y) are also
    # a superset of `Wafer`'s, so "rolls up if its keys contain yours" would fold every die
    # atom into wafer-scope reads - 160M of them by construction. The relationship being an
    # explicit statement is the difference between an aggregation unit and a coincidence of
    # spelling.
    # ⚠️ `leg` is not an entity.  It is a human-planned experiment-unit value
    # asserted by bonding_map for a region of this Wafer.  The claim predicate below keeps
    # that provenance while the physical map retains cell membership.
    "Product":   {"class": "issued",   "keys": ["product"],   "semi_ref": None,
                  "label_ko": "제품"},
    "Equipment": {"class": "issued",   "keys": ["equipment"], "semi_ref": "E10",
                  "label_ko": "장비"},
    # 🔴 `rev` IS PART OF THE IDENTITY, NOT AN ATTRIBUTE OF IT (PHYSICS_ONTOLOGY_SETUP
    # §3). A recipe revision is a NEW REGISTRATION, never an edit of an existing subject.
    # The consequence is the reason: the ledger is append-only, so if `rev` were an
    # attribute the only way to record rev5 would be to supersede rev4's atoms - and the
    # evidence for every wafer that actually ran under rev4 would stop being reachable.
    # With `rev` in the key the two revisions are two subjects, both permanently
    # assertable, and "what changed between rev4 and rev5" is a diff of two subjects'
    # `has_param` claims rather than a history reconstruction.
    "Recipe":    {"class": "issued",   "keys": ["recipe", "rev"], "semi_ref": "E40 recipe",
                  "label_ko": "레시피"},
    "Die":       {"class": "composed", "keys": ["wafer", "x", "y"], "semi_ref": "E142 location",
                  "label_ko": "다이"},
}

ISSUED_TYPES = frozenset(k for k, v in ENTITY_TYPES.items() if v["class"] == "issued")


#: The seven. `status`/`since`/`superseded_by` are the §4.3 signature fields; they are
#: carried even though nothing is deprecated yet, because the day something is, the
#: field has to already exist or the deprecation has nowhere to be written.
PREDICATES = {
    # ---------------------------------------------------------------- §4.1 canonical
    "register": {
        "label_ko": "등록",
        "status": "active", "since": 1, "layer": "canonical",
        "subject": ["Lot", "Wafer", "Product", "Equipment", "Recipe"],
        "object": None,                       # ∅ - see module docstring
        "qualifiers": [],
        "unit": None, "semi_ref": "local", "superseded_by": None,
        # Existence itself. Reached with a lot and never passed through - there is no
        # object to pass through TO.
        "traversable": False, "direction": None,
    },
    "pin": {
        "label_ko": "핀(사람 확정)",
        "status": "active", "since": 1, "layer": "canonical",
        "subject": ["Lot", "Wafer", "Product", "Equipment", "Recipe", "Die"],
        "object": {"kind": "event_ref"},
        "qualifiers": [],
        "unit": None, "semi_ref": "local", "superseded_by": None,
        "traversable": None, "direction": None,
    },
    "same_as": {
        "label_ko": "동일 개체",
        "status": "reserved", "since": 1, "layer": "canonical",
        "subject": ["Lot", "Wafer", "Product", "Equipment", "Recipe", "Die"],
        "object": {"kind": "entity_ref",
                   "types": ["Lot", "Wafer", "Product", "Equipment", "Recipe", "Die"]},
        "qualifiers": [],
        "unit": None, "semi_ref": "local", "superseded_by": None,
        # 🔴 Identity merge WILL be traversable the day it is emitted - a walk that stops
        # at an alias answers about half an entity. It stays out of the walk while its
        # status is `reserved` so that opening it is one deliberate edit HERE, with the
        # vocabulary-pinning test as its ruling, rather than a shape that arrives with the
        # first atom.
        "traversable": None, "direction": None,
    },
    # ---------------------------------------------------------------- §4.2 ontology
    "derived_from": {
        "label_ko": "유래",
        "status": "active", "since": 1, "layer": "ontology",
        "subject": ["Lot"],
        "object": {"kind": "entity_ref", "types": ["Lot"]},
        "qualifiers": [],
        "unit": None, "semi_ref": "E90 genealogy", "superseded_by": None,
        # 🔴 THE ONLY EDGE THE WALK RECURSES THROUGH. `ledger_trace`'s recursive CTE reads
        # this declaration for the predicate it follows and for the direction it follows
        # it in: subject (child) -> object (parent).
        "traversable": True, "direction": "subject_to_object",
    },
    "slot_map": {
        "label_ko": "슬롯 대응",
        "status": "active", "since": 1, "layer": "ontology",
        "subject": ["Lot"],
        "object": {"kind": "entity_ref", "types": ["Lot"]},
        # `from`/`to` are §4.2's own words. `wafer` is this implementation's addition
        # and it is REQUIRED, not optional: atomicity check ① asks whether the atom is
        # true standing alone, and "slot 10 became slot 02" standing alone does not say
        # which substrate moved. The wafer is also the evidence the pairing was derived
        # from, so an atom that carries it can be argued with.
        "qualifiers": ["from", "to", "wafer"],
        "unit": None, "semi_ref": "E90", "superseded_by": None,
        # Annotation. Its object IS a lot, so it looks traversable - and following it
        # would double-count: `derived_from` already reached that lot, and a slot map is
        # what is SAID about the pair rather than another way to get there.
        "traversable": False, "direction": None,
    },
    "has_wafer": {
        "label_ko": "웨이퍼 보유",
        "status": "active", "since": 1, "layer": "ontology",
        "subject": ["Lot"],
        "object": {"kind": "entity_ref", "types": ["Wafer"]},
        "qualifiers": ["slot"],
        "unit": None, "semi_ref": "E90", "superseded_by": None,
        # Annotation: membership of a lot the walk already reached. Bounded by slots per
        # lot, which is why it is safe to fetch with the neighbourhood - unlike `observed`.
        "traversable": False, "direction": None,
    },
    "frame_confirmed": {
        "label_ko": "프레임 확정",
        "status": "reserved", "since": 1, "layer": "ontology",
        "subject": ["Wafer"],
        "object": {"kind": "value"},
        "qualifiers": [],
        "unit": None, "semi_ref": "E142 coordinate system", "superseded_by": None,
        "traversable": None, "direction": None,
    },
    # ------------------------------------------------------- §4.2 ontology, slice 2
    # 🔴 THE RESERVED PREDICATE, OPENED. `CANONICAL_LEDGER_DESIGN.md` §4.2 reserved
    # `processed_with` (E40) from the start and PHYSICS_ONTOLOGY_SETUP §2 is where the
    # need was demonstrated: the system held logistics (lots, splits) and observations
    # (measurements, voids) but had nowhere for the CAUSE to live. Opening it takes the
    # vocabulary from seven words to nine, which is a ruling and not a drift -
    # `test_ledger_l1_unit.py::test_v0_vocabulary_is_exactly_seven_words` is where that
    # ruling is written down, and it is the reason a tenth word cannot arrive quietly.
    #
    # WHY THE OBJECT IS A `value` AND NOT AN `entity_ref`
    # ---------------------------------------------------
    # A process occurrence says only which STEP ran under which RECIPE. Equipment,
    # families, actuals and setpoints may remain as legacy extra payload, but they are not
    # part of this word's required contract and selection comparison never candidates
    # them. Physical numeric observations belong to the separate `measured` predicate.
    "processed_with": {
        "label_ko": "공정 처리",
        "status": "active", "since": 2, "layer": "ontology",
        "subject": ["Wafer"],
        # `required` is checked by `check_signature`; see the note there. Without it a
        # `value` object would be structurally unchecked, and a signature that checks
        # nothing is the decoy declaration ruling R-2026-08-13-D put an end to.
        "object": {"kind": "value", "required": ["step", "recipe"]},
        "qualifiers": [],
        "unit": None, "semi_ref": "E40 process job", "superseded_by": None,
        # 🔴 NOT IN THE WALK, and today that is enforced by an ACCIDENT worth naming: the
        # equipment and the recipe live inside a `value` payload rather than as entities,
        # so there is structurally nothing to traverse to. The day equipment becomes an
        # entity that firewall disappears - and this declaration is what keeps the answer
        # the same when it does. A hub with thousands of wafers is exactly what a walk
        # must not pass through.
        "traversable": None, "direction": None,
    },
    # One atom per SETPOINT (PHYSICS_ONTOLOGY_SETUP §3). Not one atom per recipe holding
    # a parameter dictionary: the diff between two revisions is then a set difference over
    # atoms rather than a structural comparison of two blobs, and a single parameter can
    # be superseded on its own when a recipe sheet is found to have been mistranscribed.
    "has_param": {
        "label_ko": "설정값",
        "status": "active", "since": 2, "layer": "ontology",
        "subject": ["Recipe"],
        "object": {"kind": "value", "required": ["param", "value", "unit"]},
        "qualifiers": [],
        "unit": None, "semi_ref": "E40 recipe parameter", "superseded_by": None,
        # A recipe is a hub by construction (one revision, every wafer that ran it).
        "traversable": None, "direction": None,
    },
    # 🔴 EVERY MOVEMENT OF A CHIP, IN ONE WORD (`PHYSICS_ONTOLOGY_SETUP` §2-bis, product
    # owner 2026-08-14). Wafer -> DT picking, DT -> bonding, a future rework return: one
    # predicate, one grammar. It ABSORBS the reserved `consumed`, because consumption is
    # a transfer OUT; `consumed` is registered only if destruction-without-movement
    # (scrap) is ever demonstrated, and it is deliberately NOT registered today.
    #
    # WHY THE SUBJECT IS THE WAFER AND NOT THE DIE
    # ---------------------------------------------
    # A die is COMPOSED (Wafer x grid), so it has no registration and no identity of its
    # own to carry through a move. The wafer is the die's permanent identity root, and
    # §5-2's rule is that the die is designated IN THE PAYLOAD. The consequence is the
    # point: the subject does not change when the chip moves. What changes is position,
    # and position is the CONTENT of the event.
    #
    # 🔴 WHY `from` AND `to` ARE STRUCTURED CONTAINERS AND NOT STEP NAMES
    # --------------------------------------------------------------------
    # The trace walk joins event N's `to` to event N+1's `from` - POSITION CONTINUITY -
    # and never on a step name. That is what makes a chain of arbitrary length work: two
    # DT hops, three, a rework return, all the same walk. §2-bis states the failure mode
    # as a rule: "단계 수를 아는 코드가 어디에도 없어야 한다". A join that assumes DT
    # happens once is a defect at that spot, and it is a defect that PASSES every test
    # written on a fixture where DT happens once.
    #
    # `die` XOR `qty`: an event either names one die or carries a count. The signature
    # cannot express XOR, so `required` holds only the two that are always present and
    # the emitter owns the exclusivity - stated here so the next author knows the check
    # is not merely missing.
    "transferred": {
        "label_ko": "이동",
        "status": "active", "since": 2, "layer": "ontology",
        "subject": ["Wafer"],
        "object": {"kind": "value", "required": ["from", "to"]},
        "qualifiers": [],
        "unit": None, "semi_ref": "E90 substrate movement", "superseded_by": None,
        # 🔴 The position-continuity walk (`to` of event N joined to `from` of event N+1)
        # is a DIFFERENT walk from the lot lineage one, over `value` containers rather
        # than entity refs. Declaring it traversable here would put it in the lineage
        # walk's fetch set, which is not what it is - so it stays out until that walk
        # exists and can declare its own semantics.
        #
        # 🔴 RE-JUDGED WHEN THE `dt_log` TRANSLATOR LANDED (2026-08-14), because the
        # standing rule is that a word joins the walk by DECISION, never by arriving. The
        # decision is unchanged and TWO OF THE THREE REASONS ARE NOT THE OBVIOUS ONE:
        #
        #   ① `True` is not merely wrong, it is UNRUNNABLE. `ledger_trace.
        #      traversal_predicate` refuses a vocabulary with more than one traversable
        #      word BY NAME - the recursive CTE joins on a value, not a set - so this
        #      would take the trace screen down rather than widen it.
        #   ② `False` (fetch as an annotation) is wrong for a reason of KIND: an
        #      annotation is something said about a lot the walk already reached, and this
        #      word's subject is a WAFER whose object is an opaque `value` container. The
        #      lot walk has nothing to attach it to.
        #   ③ ⚠️ CARGO DOES NOT DECIDE IT, and saying it did would be a borrowed argument.
        #      MEASURED on `assy_manager` after the `dt_log` backfill: 72,485 `transferred`
        #      atoms over 3,378 wafers, MAX 34 PER WAFER (28 of them from `dt_log`). That
        #      is the same order as `has_wafer`, which IS fetched at max 62 per lot - so
        #      the volume argument that keeps `observed` out (R-2026-08-14-D addendum ①)
        #      does NOT apply here. It is a watch item, not the reason: a core wafer feeding
        #      DT jobs for its whole life grows this number, and the day it reaches
        #      `observed`'s order the cap declared by R-2026-08-14-E is what should answer.
        "traversable": None, "direction": None,
    },
    # ------------------------------------------------------- §4.2 ontology, slice 3
    # 🔴 THE OBSERVATION WORD (ruling R-2026-08-14-D, `MI_LEDGER_SCHEMA_PROPOSAL` §6-bis).
    # Voids, delaminations, fab defects and a human's microscope note are ONE utterance
    # shape - "this was found, here, this big, by this look" - and §6-bis's whole finding
    # is that they differ from a measurement in the OBJECT only. `measured` (the value of a
    # physical quantity) is its sibling and is deliberately NOT registered today: no
    # translator emits it yet, and this vocabulary registers a word when the need is
    # demonstrated rather than when it is anticipated.
    #
    # WHY THE SUBJECT IS THE WAFER AND THE CHIP IS IN THE PAYLOAD
    # ------------------------------------------------------------
    # Same rule as `transferred`, for the same reason: `Die` is COMPOSED, so it has no
    # registration and no identity to hang an observation on. §6-bis says subject = Wafer
    # with the chip coordinates carried, and §5-2 says the die is designated in the
    # payload. The consequence is that every observation of every chip on a substrate
    # folds under ONE subject, which is what makes "이 웨이퍼의 보이드" one query.
    #
    # 🔴 WHY `run_uid` IS REQUIRED - THE DENOMINATOR RULE, INSIDE THE LEDGER
    # -----------------------------------------------------------------------
    # 「3 voids」means nothing without「out of how many scans」. The scan population lives
    # in `inspection_run`, and an observation atom that did not name its run would put the
    # ledger in the position the source tables are already out of: countable findings with
    # no countable denominator, so every rate computed from the ledger alone would be
    # arithmetic over whatever rows happened to be nearby. Required rather than merely
    # documented, because `required` is the enforcement point a `value` object has
    # (R-2026-08-13-D) - and refusing an observation with no run is the correct outcome,
    # not an inconvenience.
    #
    # ⚠️ §6-ter's arbitrary human observation (an OM note) HAS no run and no denominator by
    # its own admission. It is not in scope today, and when it lands this required field is
    # what will force that to be a ruling - "an observation with no denominator" is a
    # decision somebody has to make out loud - rather than a silently absent key.
    #
    # WHAT IS NOT HERE: `class` (§6-quater - a defect's class is a CLAIM, carried when the
    # source utters one and re-assertable by a human later, so it is a payload field and
    # never a column), and any pass/fail (the threshold is a recipe parameter; storing a
    # verdict makes history un-re-judgeable).
    # A human experiment plan assigns regions of one physical Wafer to bonding units.
    # ``unit_id`` is a VALUE in that assertion, not a second entity identity.  ``map_ref``
    # points back to the physical bonding_map whose cells define the region; cells are not
    # expanded into ledger atoms.
    "assigned_to_experiment": {
        "label_ko": "실험 단위 배정",
        "status": "active", "since": 5, "layer": "ontology",
        "subject": ["Wafer"],
        "object": {"kind": "value",
                   "required": ["experiment_type", "unit_id", "map_ref"]},
        "qualifiers": [],
        "unit": None, "semi_ref": "DOE bonding map", "superseded_by": None,
        "traversable": None, "direction": None,
    },
    "observed": {
        "label_ko": "관측",
        "status": "active", "since": 3, "layer": "ontology",
        "subject": ["Wafer"],
        "object": {"kind": "value",
                   "required": ["finding_kind", "method", "run_uid"]},
        "qualifiers": [],
        "unit": None, "semi_ref": "E142 defect location", "superseded_by": None,
        # 🔴 `None`, AND IT IS THE WHOLE OF ADDENDUM ① (R-2026-08-14-D). The walk fetches
        # every claim of every lot it reaches; a wafer carries tens of thousands of
        # observations, so putting this word in that set would make the trace screen die on
        # the day the translator first succeeds. Observations are read by a SCOPED request
        # (kind, period) - `GET /api/ledger/siblings` and the console's own queries - and
        # never by reaching a lot.
        "traversable": None, "direction": None,
    },
    # The physical-quantity sibling of `observed` (MI schema §6-bis).  The UI calls its
    # comparison category `measured_as`, but that is a presentation namespace, not a
    # second ledger word.  Process telemetry remains `processed_with.params_actual`;
    # `measured` is for a separate metrology act with its own method/run evidence.
    #
    # Missingness is part of the utterance, never reconstructed from a numeric sentinel.
    # A recorded result must carry the actual value and run identity.  The other three
    # states must OMIT `value`: accepting even JSON null would invite a consumer to turn
    # it into numeric zero.  `check_signature` enforces this declarative state contract.
    "measured": {
        "label_ko": "계측",
        "status": "active", "since": 4, "layer": "ontology",
        "subject": ["Wafer"],
        "object": {
            "kind": "value",
            "required": ["metric", "unit", "method", "state"],
            "state_contract": {
                "field": "state",
                "allowed": ["recorded", "missing", "not_performed", "unknown"],
                "value_field": "value",
                "value_required_for": ["recorded"],
                "value_forbidden_for": ["missing", "not_performed", "unknown"],
                "required_by_state": {"recorded": ["run_uid"]},
            },
        },
        "qualifiers": [],
        "unit": None, "semi_ref": "E16 measurement", "superseded_by": None,
        # High-cardinality metrology is read only by a bounded, subject-scoped request.
        "traversable": None, "direction": None,
    },
}

#: 🔴 THE CODE-LOADED SET, NAMED. `PREDICATES` is what this MODULE declares, and
#: `test_ledger_l1_unit.py` pins it - ruling R-2026-08-15-M ④ says in as many words that
#: the fixed test pins「코드가 싣는 집합」and that the config extension joins as a separate
#: list. Reading `PREDICATES` therefore still means exactly what it meant yesterday, and
#: everything that has to ask about the WHOLE language calls `all_predicates()` below.
CODE_PREDICATES = PREDICATES

#: The directions a traversable edge may be followed in (ruling R-2026-08-14-E). Closed,
#: because a direction nothing implements is a walk that silently goes the wrong way -
#: `ledger_trace` refuses a declaration it cannot execute BY NAME rather than falling back
#: to the direction it happens to have hard-coded.
WALK_DIRECTIONS = frozenset({"subject_to_object", "object_to_subject"})

#: The statuses a declared word may carry. `retired` is the ONLY way a word leaves
#: circulation (ruling R-2026-08-15-M ③): atoms are already lying in the ledger under it,
#: so deleting the declaration would make those atoms unreadable rather than obsolete.
PREDICATE_STATUSES = ("active", "reserved", "retired")

#: The two layers, §4.1 / §4.2. `canonical` is code plus a ruling and is NOT reachable
#: from a screen; `ontology` is the one that grows.
LAYER_CANONICAL = "canonical"
LAYER_ONTOLOGY = "ontology"
EDITABLE_LAYER = LAYER_ONTOLOGY

# ===========================================================================
# THE ONTOLOGY LAYER'S SECOND SOURCE - DECLARATION (ruling R-2026-08-15-M ②/④)
# ===========================================================================
# The split this implements is NOT new. The module docstring above draws it already:
# §4.1 is「사실상 동결」and §4.2「append-only로 성장」. What was missing is that a layer
# documented as growing could only be grown by editing this file, so the growth needed a
# developer and a deploy.
#
# 🔴 WHY A SEPARATE FILE AND NOT A KEY IN `ledger_config.json`
# -------------------------------------------------------------
# `ledger_config.json` is loaded through `ledger.config.validate`, which raises on the
# whole file when ANY source declaration is malformed. Words and sources would then share
# a failure: a typo in a column mapping would take the vocabulary down with it, and a
# vocabulary the gate cannot read refuses every atom of every source. Two files means a
# broken source refuses that source, and a broken word list refuses words - each failure
# stays the size of what actually failed.
#
# 🔴 WHY THE LOADER NEVER RAISES
# --------------------------------
# `ledger.config.load` raises because a source with no declared time column has no honest
# behaviour to fall back on. This one has one: the code-loaded set, which is the ledger
# every process ran on before this file existed. A malformed extension therefore
# DEGRADES to code-only and says so through `extension_status()` - which is what
# `/admin/config/resolve` renders - rather than taking five processes down over a stray
# comma in an operator's edit.
EXTENSION_FILENAME = "ledger_vocabulary.json"

#: 🔴 EVERY ONE OF THESE IS REQUIRED, AND `traversable` IS REQUIRED AS A *KEY*
#: (ruling R-2026-08-15-M ②). The tri-state's third state is `None`, so "absent" and
#: "explicitly uncollected" would be the same value if presence were not checked
#: separately - and a defaulted `traversable` is a walk semantics nobody chose. The
#: check below therefore asks `"traversable" in declaration`, never `.get(...)`.
SIGNATURE_FIELDS = ("label_ko", "subject", "object", "traversable", "direction",
                    "since", "layer", "status")

#: Loaded lazily and cached with the file's mtime+size, because five processes import this
#: module and a per-lookup stat on a hot path is a cost with no reader. `reset_cache()` is
#: wired into `/admin/reload-configs`, so an edit takes effect without a restart - which is
#: the entire point of the round this arrived in.
_EXTENSION_CACHE = {}


def extension_path() -> str:
    """Where the config extension lives. Same directory as every other operator config."""
    try:
        import paths
        config_dir = paths.CONFIG_DIR
    except Exception:
        config_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
    return os.path.join(config_dir, EXTENSION_FILENAME)


def reset_cache():
    """Forget the loaded extension. Called by `/admin/reload-configs`."""
    _EXTENSION_CACHE.clear()


def _stat_key(path):
    try:
        info = os.stat(path)
        return (info.st_mtime_ns, info.st_size)
    except OSError:
        return None


def _load_extension():
    """`(predicates, status)`. Never raises - see the block comment above."""
    path = extension_path()
    key = _stat_key(path)
    cached = _EXTENSION_CACHE.get("value")
    if cached is not None and _EXTENSION_CACHE.get("key") == key:
        return cached

    status = {"path": path, "exists": key is not None, "ok": True, "error": None,
              "count": 0}
    predicates = {}
    if key is not None:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            declared = (raw or {}).get("predicates")
            if not isinstance(declared, dict):
                raise ValueError("'predicates' must be an object mapping name -> signature")
            for name, declaration in declared.items():
                if str(name).startswith("__"):
                    continue
                violations = check_predicate_declaration(name, declaration,
                                                         against=predicates)
                if violations:
                    raise ValueError(
                        f"predicate '{name}': " + "; ".join(v["detail_en"]
                                                            for v in violations))
                predicates[name] = _normalise_declaration(declaration)
            status["count"] = len(predicates)
        except Exception as exc:
            # The whole file, not the one entry: a partially loaded vocabulary is a
            # vocabulary whose contents depend on dict order, and the gate would then
            # accept a word on one process and refuse it on another.
            predicates = {}
            status.update(ok=False, error=f"{exc.__class__.__name__}: {exc}", count=0)

    value = (predicates, status)
    _EXTENSION_CACHE["key"] = key
    _EXTENSION_CACHE["value"] = value
    _EXTENSION_CACHE.pop("merged", None)   # the merged view is now stale by construction
    return value


def _normalise_declaration(declaration: dict) -> dict:
    """A config entry in the exact shape a code entry has. Missing OPTIONAL keys only."""
    entry = dict(declaration)
    entry.setdefault("qualifiers", [])
    entry.setdefault("unit", None)
    entry.setdefault("semi_ref", None)
    entry.setdefault("superseded_by", None)
    return entry


def config_predicates() -> dict:
    """The words the operator declared. `{}` when there is no file or it is unreadable."""
    return dict(_load_extension()[0])


def extension_status() -> dict:
    """Whether the extension file loaded, and why not. Rendered by `/admin/config/resolve`."""
    return dict(_load_extension()[1])


def all_predicates() -> dict:
    """🔴 THE WHOLE LANGUAGE, every entry stamped with where it came from.

    Everything that ASKS A QUESTION OF THE VOCABULARY reads this - the gate's signature
    check, the walk's fetch set, the structure view. `PREDICATES` stays the code-loaded
    set so the v0 pinning test keeps pinning what it was written to pin (R-M ④), and the
    two are related by construction rather than by a second list somebody maintains.

    A config entry can never shadow a code one: the code set is applied LAST. The
    declaration checker already refuses a duplicate by name, so this is the second net,
    and it is the one that holds when a file is edited outside the admin route.

    ⚠️ THE RETURNED DICT IS SHARED AND MUST BE TREATED AS READ-ONLY. `check_signature`
    calls this once per ATOM, so building a fresh dict per call would put an O(vocabulary)
    allocation on a path that runs ten million times - the cost this project measures
    everything against. Callers that need to mutate copy it themselves.
    """
    merged = _EXTENSION_CACHE.get("merged")
    # 🔴 THE CACHE IS KEYED ON THE `PREDICATES` OBJECT ITSELF, NOT ONLY ON THE FILE.
    # This view is derived from TWO mutable things - the extension file and this module's
    # `PREDICATES` - and the first version keyed only the file. MEASURED failure: a suite
    # that swaps the whole vocabulary (`test_ledger_structure_pg`) also repoints
    # `paths.CONFIG_DIR`, which dropped the merged view WHILE THE FAKE WAS INSTALLED; the
    # rebuild cached the fake, the restore changed nothing the key could see, and the NEXT
    # test file got a vocabulary with zero traversable predicates and an error about a
    # recursive CTE. An identity check is O(1), needs no syscall, and catches exactly the
    # rebinding that a stat cannot.
    if merged is not None and _EXTENSION_CACHE.get("merged_from") is PREDICATES:
        return merged
    # 🔴 NO `os.stat` ON THIS PATH. The freshness check lives in `_load_extension`, which
    # request-path callers (`config_predicates`, `extension_status`) go through and which
    # drops this cache when the file's stat key moves; the daemons that call this per atom
    # are refreshed by `reset_cache()` on `/admin/reload-configs`, which is the declared
    # mechanism for「재기동 없이 반영」. A stat per atom would be ten million syscalls.
    config = config_predicates()
    merged = {}
    for name, sig in config.items():
        merged[name] = dict(sig, origin="code" if name in PREDICATES else "config")
    for name, sig in PREDICATES.items():
        merged[name] = dict(sig, origin="code")
    _EXTENSION_CACHE["merged"] = merged
    _EXTENSION_CACHE["merged_from"] = PREDICATES
    return merged


def predicate_origin(predicate: str):
    """`"code"` / `"config"` / `None`. What the structure view labels a word with."""
    if predicate in PREDICATES:
        return "code"
    if predicate in config_predicates():
        return "config"
    return None


def emittable() -> frozenset:
    """Predicates a translator may EMIT, across BOTH sources.

    A function rather than the module-level constant it used to be: a frozenset computed
    at import time would have frozen the config layer's contents at whatever the file said
    when the first process imported this module, and `/admin/reload-configs` could never
    have changed it. `reserved` entries are declared so the vocabulary is complete and so a
    future emitter does not re-mint the word under a second spelling, but emitting one
    today is an undeclared-vocabulary refusal.
    """
    return frozenset(name for name, sig in all_predicates().items()
                     if sig.get("status") == "active")


def _violation(code, field, detail_ko, detail_en):
    """One refusal, in the shape the admin route returns and the loader logs.

    Two renderings of one judgement on purpose: `detail_ko` is what the operator reads on
    the screen (this project's rule is that every human sentence is built by the server),
    and `detail_en` is what goes in a process log where Korean would be mojibake on a
    console the operator does not own.
    """
    return {"code": code, "field": field, "detail_ko": detail_ko, "detail_en": detail_en}


#: The closed refusal set for a predicate declaration. Closed for the reason the gate's
#: reasons are: a code invented at a call site is a refusal the screen cannot render.
DECL_REFUSALS = (
    "signature_incomplete", "invalid_identifier", "undeclared_entity_type",
    "undeclared_object_kind", "duplicate_predicate", "canonical_layer_forbidden",
    "invalid_value", "traversable_true_unavailable", "retire_target_unknown",
)

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def check_predicate_declaration(name, declaration, against: dict = None) -> list:
    """Violations of a CONFIG predicate declaration. Empty list = it may be saved.

    🔴 THE COMPLETENESS RULE IS THE POINT (R-2026-08-15-M ②). An incomplete signature is a
    word the gate cannot check, and a word the gate cannot check is a write path with no
    gate - which is the thing this whole subsystem exists to not be. So every field is
    required, and the refusal names the field rather than saying "invalid".

    `against` is the set already accepted in this same file, so a file declaring one name
    twice is refused rather than silently keeping whichever came last.
    """
    out = []
    against = against or {}

    if not isinstance(name, str) or not _NAME_RE.match(name):
        out.append(_violation(
            "invalid_identifier", "name",
            f"술어 이름 '{name}'은 소문자·숫자·밑줄만 쓸 수 있고 문자로 시작해야 합니다. "
            f"이 이름은 SQL과 JSON 양쪽에서 그대로 쓰이는 식별자입니다.",
            f"predicate name {name!r} must match {_NAME_RE.pattern}"))
        return out
    if name in PREDICATES:
        out.append(_violation(
            "duplicate_predicate", "name",
            f"'{name}'은 코드가 이미 싣고 있는 술어입니다. 선언으로 덮어쓸 수 없습니다 — "
            f"코드가 싣는 낱말을 화면이 바꾸면 원자의 뜻이 배포마다 달라집니다.",
            f"predicate {name!r} is already declared in code"))
    if name in against:
        out.append(_violation(
            "duplicate_predicate", "name",
            f"'{name}'이 선언 파일 안에 두 번 나옵니다.",
            f"predicate {name!r} is declared twice in the extension file"))
    if name in PROJECTION_ONLY_WORDS:
        out.append(_violation(
            "invalid_identifier", "name",
            f"'{name}'은 투영(projection)의 상태 낱말이라 원장에 실릴 수 없습니다.",
            f"{name!r} is a projection-only word"))
    if not isinstance(declaration, dict):
        out.append(_violation(
            "signature_incomplete", None,
            "술어 선언은 객체여야 합니다.", "declaration must be an object"))
        return out

    # --- ② 서명 완결성. 없는 필드를 먼저 전부 세고 나서 값들을 본다: 화면이 빈칸 하나만
    #     고치고 다시 거절당하는 왕복을 하지 않도록.
    absent = [field for field in SIGNATURE_FIELDS if field not in declaration]
    if absent:
        out.append(_violation(
            "signature_incomplete", absent[0],
            f"서명이 완결되지 않았습니다 — {', '.join(absent)}가 없습니다. 게이트는 서명으로 "
            f"원자를 검사하므로, 빠진 필드가 하나라도 있으면 그 낱말은 검사할 수 없는 "
            f"낱말이 됩니다(= 검사 없는 쓰기 경로).",
            f"signature incomplete: missing {', '.join(absent)}"))
        return out

    layer = declaration.get("layer")
    if layer != LAYER_ONTOLOGY:
        out.append(_violation(
            "canonical_layer_forbidden", "layer",
            f"layer는 '{LAYER_ONTOLOGY}'만 선언할 수 있습니다(받은 값: {layer!r}). "
            f"canonical 층은 기록의 문법이라 코드와 판정으로만 늘어납니다.",
            f"layer must be {LAYER_ONTOLOGY!r}, got {layer!r}"))

    if not str(declaration.get("label_ko") or "").strip():
        out.append(_violation(
            "signature_incomplete", "label_ko",
            "label_ko가 비었습니다. 구조 뷰가 이 낱말을 한국어로 그리므로 라벨은 낱말과 "
            "같은 자리에서 와야 합니다.",
            "label_ko is blank"))

    status = declaration.get("status")
    if status not in PREDICATE_STATUSES:
        out.append(_violation(
            "invalid_value", "status",
            f"status는 {', '.join(PREDICATE_STATUSES)} 중 하나여야 합니다(받은 값: "
            f"{status!r}).",
            f"status must be one of {PREDICATE_STATUSES}, got {status!r}"))

    since = declaration.get("since")
    if not isinstance(since, int) or isinstance(since, bool) or since < 1:
        out.append(_violation(
            "invalid_value", "since",
            f"since는 1 이상의 정수여야 합니다(받은 값: {since!r}). 어느 슬라이스에서 "
            f"이 낱말이 생겼는지가 원자를 되짚는 기준입니다.",
            f"since must be an int >= 1, got {since!r}"))

    subject = declaration.get("subject")
    if not isinstance(subject, list) or not subject:
        out.append(_violation(
            "signature_incomplete", "subject",
            "subject는 이 술어가 받을 수 있는 주어 타입의 비어 있지 않은 목록이어야 "
            "합니다.", "subject must be a non-empty list"))
    else:
        unknown = [s for s in subject if s not in ENTITY_TYPES]
        if unknown:
            out.append(_violation(
                "undeclared_entity_type", "subject",
                f"subject의 {', '.join(map(str, unknown))}는 선언된 개체 타입이 아닙니다"
                f"(선언된 것: {', '.join(sorted(ENTITY_TYPES))}). 개체 타입을 늘리는 것은 "
                f"config가 아니라 어휘 판정입니다.",
                f"subject names undeclared entity type(s) {unknown}"))

    out.extend(_check_object_declaration(declaration.get("object")))
    out.extend(_check_walk_fields(name, declaration, against))

    qualifiers = declaration.get("qualifiers", [])
    if not isinstance(qualifiers, list) or any(not isinstance(q, str) or not q.strip()
                                               for q in qualifiers):
        out.append(_violation(
            "invalid_value", "qualifiers",
            "qualifiers는 문자열 목록이어야 합니다(없으면 빈 목록).",
            "qualifiers must be a list of non-blank strings"))

    superseded_by = declaration.get("superseded_by")
    if superseded_by is not None:
        known = set(PREDICATES) | set(against)
        if superseded_by not in known:
            out.append(_violation(
                "retire_target_unknown", "superseded_by",
                f"superseded_by가 가리키는 '{superseded_by}'는 선언된 술어가 아닙니다.",
                f"superseded_by names undeclared predicate {superseded_by!r}"))
    return out


def _check_object_declaration(declared_object) -> list:
    """`object` is either ∅ or a kind with something the gate can actually check."""
    out = []
    if declared_object is None:
        # ∅ is legal for `register` ALONE and the DDL's CHECK says so. An ontology word
        # with no object would be a word that says only "this happened" about a subject -
        # `register` in a second spelling, which §4.1 owns.
        return [_violation(
            "signature_incomplete", "object",
            "object가 ∅입니다. 목적어 없는 술어는 canonical의 register뿐이고, ontology 층은 "
            "무엇에 대해 무엇을 말하는지를 실어야 합니다.",
            "object must not be null for an ontology predicate")]
    if not isinstance(declared_object, dict):
        return [_violation("signature_incomplete", "object",
                           "object는 {kind, ...} 객체여야 합니다.",
                           "object must be an object")]
    kind = declared_object.get("kind")
    if kind not in OBJECT_KINDS:
        out.append(_violation(
            "undeclared_object_kind", "object.kind",
            f"object.kind는 {', '.join(sorted(OBJECT_KINDS))} 중 하나여야 합니다"
            f"(받은 값: {kind!r}).",
            f"object.kind must be one of {sorted(OBJECT_KINDS)}, got {kind!r}"))
        return out
    if kind == "value":
        required = declared_object.get("required")
        # 🔴 NON-EMPTY, and this is ruling R-2026-08-13-D one column over: `required` is
        # the ONLY enforcement point a `value` object has, so a value object without one
        # is a signature that checks nothing - the decoy declaration, declared.
        if not isinstance(required, list) or not required or any(
                not isinstance(f, str) or not f.strip() for f in required):
            out.append(_violation(
                "signature_incomplete", "object.required",
                "object.kind가 'value'면 required에 반드시 실려야 하는 필드 이름을 "
                "하나 이상 적어야 합니다. required가 없는 value 목적어는 게이트가 아무것도 "
                "검사하지 않는 서명입니다.",
                "a value object needs a non-empty `required` list"))
    elif kind == "entity_ref":
        types = declared_object.get("types")
        if not isinstance(types, list) or not types:
            out.append(_violation(
                "signature_incomplete", "object.types",
                "object.kind가 'entity_ref'면 가리킬 수 있는 개체 타입 목록(types)이 "
                "필요합니다.", "an entity_ref object needs a non-empty `types` list"))
        else:
            unknown = [t for t in types if t not in ENTITY_TYPES]
            if unknown:
                out.append(_violation(
                    "undeclared_entity_type", "object.types",
                    f"object.types의 {', '.join(map(str, unknown))}는 선언된 개체 "
                    f"타입이 아닙니다.",
                    f"object.types names undeclared entity type(s) {unknown}"))
    return out


def _check_walk_fields(name, declaration, against: dict = None) -> list:
    """`traversable` / `direction`, including the one the WALK cannot execute.

    🔴 `traversable: true` is refused while another traversable word exists, and the
    refusal is not squeamishness: `ledger_trace.traversal_predicate` REFUSES BY NAME a
    vocabulary with more than one traversable word (its recursive CTE joins on a value,
    not a set). Accepting the declaration here would take the trace screen down at the
    next request - a save that breaks a different screen, with the operator holding a
    green save message. The three states stay selectable; the one this walk cannot run
    says so at save time instead of at read time.
    """
    out = []
    traversable = declaration.get("traversable")
    if traversable not in (True, False, None):
        out.append(_violation(
            "invalid_value", "traversable",
            f"traversable은 true(재귀 통과) / false(도달만) / null(미수집) 셋 중 하나를 "
            f"«명시»해야 합니다(받은 값: {traversable!r}).",
            f"traversable must be True, False or None, got {traversable!r}"))
        return out

    direction = declaration.get("direction")
    if traversable is True:
        # 🔴 `PREDICATES` + the entries already accepted, NEVER `all_predicates()`. The
        # loader calls this function WHILE it is assembling the config layer, so reading
        # the merged view here would re-enter the loader and hang. The union below is the
        # same set the loader is building towards, one entry earlier.
        known = dict(against or {})
        known.update(PREDICATES)
        already = [n for n, sig in known.items()
                   if sig.get("traversable") is True and n != name]
        if already:
            out.append(_violation(
                "traversable_true_unavailable", "traversable",
                f"traversable=true는 지금 선택할 수 없습니다 — 걷기는 통과 술어를 정확히 "
                f"하나만 실행할 수 있고 이미 '{', '.join(sorted(already))}'가 그 자리에 "
                f"있습니다. 둘째 통과 엣지는 재귀 질의를 값이 아니라 집합으로 조인하도록 "
                f"바꾸는 «측정된 변경»이라 선언으로 켤 수 없습니다. 주석형이면 false"
                f"(도달만), 걷기가 안 가져와야 하면 null을 고르세요.",
                f"a second traversable predicate is not executable by the walk "
                f"(existing: {sorted(already)})"))
        elif direction not in WALK_DIRECTIONS:
            out.append(_violation(
                "invalid_value", "direction",
                f"traversable=true면 direction은 {', '.join(sorted(WALK_DIRECTIONS))} "
                f"중 하나여야 합니다(받은 값: {direction!r}).",
                f"direction must be one of {sorted(WALK_DIRECTIONS)}, got {direction!r}"))
    elif direction is not None:
        out.append(_violation(
            "invalid_value", "direction",
            f"traversable이 {traversable!r}인데 direction이 {direction!r}입니다. 아무도 "
            f"걷지 않는 엣지의 방향은 아무것도 구속하지 않습니다 — null이어야 합니다.",
            f"direction {direction!r} on a non-traversable predicate binds nothing"))
    return out


def walk_predicates():
    """Every predicate the lineage walk may FETCH - traversable ones and annotations.

    🔴 This is what `ledger_trace.LINEAGE_PREDICATES` used to spell by hand. Derived, so
    admitting a word to the walk is a declaration change plus the vocabulary-pinning test,
    and EXCLUDING one (`observed`) is a thing the vocabulary can actually say.
    """
    return tuple(sorted(name for name, sig in all_predicates().items()
                        if sig.get("traversable") is not None))


def traversable_predicates():
    """The predicates the walk RECURSES through. A subset of `walk_predicates()`."""
    return tuple(sorted(name for name, sig in all_predicates().items()
                        if sig.get("traversable") is True))


def walk_direction(predicate):
    """Which way a traversable edge is followed, or `None` if it is not traversed."""
    return (all_predicates().get(predicate) or {}).get("direction")


def check_walk_declaration():
    """Violations of the walk declaration's own rules. Pure; the test is the enforcer.

    Two directions of the same rule, because a declaration that can only ever be
    consistent-by-accident is the decoy again: a traversable edge with no direction would
    be walked whichever way the SQL happened to be written, and a direction on an edge
    nobody walks would teach a reader a constraint that binds nothing.
    """
    violations = []
    for name, sig in all_predicates().items():
        if "traversable" not in sig:
            violations.append(
                f"predicate '{name}' does not declare `traversable`. Three states are "
                f"legal (True = the walk recurses, False = annotation only, None = the "
                f"walk never fetches it); an absent field is a fourth that means nothing.")
            continue
        traversable = sig.get("traversable")
        direction = sig.get("direction")
        if traversable is True:
            if direction not in WALK_DIRECTIONS:
                violations.append(
                    f"predicate '{name}' is traversable but declares direction "
                    f"{direction!r}, which is not one of {sorted(WALK_DIRECTIONS)}")
        elif direction is not None:
            violations.append(
                f"predicate '{name}' is not traversable (traversable={traversable!r}) "
                f"but declares direction {direction!r} - a direction on an edge nobody "
                f"walks binds nothing")
    return violations


#: The projection's state words (§4.2, third vocabulary). Named here for ONE reason: so
#: the gate can refuse them by name. "This word belongs to the cache, never to the
#: ledger" is a rule that only exists if something enforces it.
PROJECTION_ONLY_WORDS = frozenset({
    "resolved", "contested", "candidate", "unresolvable", "pinned",
})


def is_declared(predicate: str) -> bool:
    """🔴 THE MERGED SET. `gate.screen_molecule` asks this to refuse an undeclared word,
    so a predicate registered from admin becomes emittable here and nowhere else."""
    return predicate in all_predicates()


def signature(predicate: str):
    return all_predicates().get(predicate)


def check_signature(predicate, subject_type, object_kind, object_payload):
    """Return a list of signature violations. Empty list = the atom fits its declaration.

    Pure - takes no connection, keeps no state, and never logs. The gate owns counting
    and announcing; this owns only the judgement, so the judgement can be unit-tested
    without a database and reused by anything else that has to ask the same question.
    """
    if predicate in PROJECTION_ONLY_WORDS:
        return [f"'{predicate}' is a PROJECTION state word (design §4.2) and may never "
                f"be written to the ledger"]

    # 🔴 THE MERGED SET, so a config-declared word is checked by exactly the machinery a
    # code-declared one is. This is the line ruling R-2026-08-15-M ④ means by「게이트의
    # 서명 검사는 합쳐진 집합을 그대로 쓴다」 - the same `required` fields, the same
    # subject list, the same entity_ref identity check, with no second code path.
    sig = all_predicates().get(predicate)
    if sig is None:
        return [f"predicate '{predicate}' is not in the closed vocabulary"]
    return check_signature_against(sig, predicate, subject_type, object_kind,
                                   object_payload)


def check_signature_against(sig, predicate, subject_type, object_kind, object_payload):
    """`check_signature` with the declaration HANDED IN rather than looked up.

    🔴 Exists for ONE caller and the reason is worth stating: the admin dry run has to
    show what a signature that is NOT YET SAVED would accept and refuse, and the only
    honest way to do that is to run the gate's own judgement over it. The alternative -
    temporarily inserting the candidate into the shared merged dict - would mutate a
    process-wide cache that live translations read, so a preview on the web server could
    change what a concurrent request's gate believes. A parameter cannot do that.
    """
    violations = []
    if sig["status"] != "active":
        # `retired` and `reserved` are different facts and the message says which:
        # retirement is a word that HAS been spoken and may not be spoken again (atoms
        # still read back), reservation is one that has not been spoken yet.
        why = ("it was RETIRED and may no longer be emitted; atoms already written under "
               "it still read back" if sig["status"] == "retired"
               else "it may not be emitted yet")
        violations.append(f"predicate '{predicate}' is declared but its status is "
                          f"'{sig['status']}' - {why}")

    if subject_type not in ENTITY_TYPES:
        violations.append(f"subject type '{subject_type}' is not a declared entity type")
    elif subject_type not in sig["subject"]:
        violations.append(
            f"predicate '{predicate}' does not accept subject type '{subject_type}' "
            f"(declared: {', '.join(sig['subject'])})")

    declared_object = sig["object"]
    if declared_object is None:
        if object_kind is not None:
            violations.append(
                f"predicate '{predicate}' takes no object, but object_kind="
                f"{object_kind!r} was supplied")
        if object_payload is not None:
            violations.append(
                f"predicate '{predicate}' takes no object, but a payload was supplied")
        return violations

    if object_kind is None:
        violations.append(f"predicate '{predicate}' requires an object of kind "
                          f"'{declared_object['kind']}' but object_kind is NULL")
        return violations
    if object_kind not in OBJECT_KINDS:
        violations.append(f"object_kind '{object_kind}' is not one of "
                          f"{sorted(OBJECT_KINDS)}")
    if object_kind != declared_object["kind"]:
        violations.append(
            f"predicate '{predicate}' declares object kind '{declared_object['kind']}' "
            f"but this atom carries '{object_kind}'")

    if object_kind == "value":
        # 🔴 A `value` object used to be structurally unchecked, which meant a predicate
        # could declare a shape in prose and the gate would accept anything at all -
        # ruling R-2026-08-13-D's decoy declaration, one column over. `required` is the
        # enforcement point, so a `processed_with` atom that forgot which step it was
        # about is refused by the same machinery that refuses an undeclared predicate.
        #
        # ⚠️ Presence, NOT truthiness. `has_param`'s `value` is legitimately `0` and
        # legitimately `False`, and a truthiness test would refuse the two setpoints most
        # worth recording. A blank STRING is still refused: it is the shape design §3's
        # concatenation incident came from.
        required = declared_object.get("required") or []
        if required:
            if not isinstance(object_payload, dict):
                violations.append(
                    f"predicate '{predicate}' declares a value object with required "
                    f"field(s) {', '.join(required)}, so the payload must be an object")
                return violations
            absent = [field for field in required
                      if field not in object_payload
                      or object_payload[field] is None
                      or (isinstance(object_payload[field], str)
                          and not object_payload[field].strip())]
            if absent:
                violations.append(
                    f"predicate '{predicate}' requires value field(s) "
                    f"{', '.join(required)}; missing or blank: {', '.join(absent)}")
        state_contract = declared_object.get("state_contract") or {}
        if state_contract and isinstance(object_payload, dict):
            state_field = state_contract["field"]
            state = object_payload.get(state_field)
            allowed = state_contract.get("allowed") or []
            if state not in allowed:
                violations.append(
                    f"predicate '{predicate}' requires {state_field} to be one of "
                    f"{', '.join(allowed)}; got {state!r}")
            else:
                state_required = (state_contract.get("required_by_state") or {}).get(
                    state, [])
                absent_for_state = [field for field in state_required
                                    if field not in object_payload
                                    or object_payload[field] is None
                                    or (isinstance(object_payload[field], str)
                                        and not object_payload[field].strip())]
                if absent_for_state:
                    violations.append(
                        f"predicate '{predicate}' state '{state}' requires field(s) "
                        f"{', '.join(absent_for_state)}")
                value_field = state_contract.get("value_field")
                if state in (state_contract.get("value_required_for") or []):
                    if (value_field not in object_payload
                            or object_payload[value_field] is None
                            or (isinstance(object_payload[value_field], str)
                                and not object_payload[value_field].strip())):
                        violations.append(
                            f"predicate '{predicate}' state '{state}' requires field "
                            f"'{value_field}'")
                if (state in (state_contract.get("value_forbidden_for") or [])
                        and value_field in object_payload):
                    violations.append(
                        f"predicate '{predicate}' state '{state}' forbids field "
                        f"'{value_field}'")
        return violations

    if object_kind == "entity_ref":
        if not isinstance(object_payload, dict):
            violations.append("an entity_ref payload must be an object with 'type' and "
                              "'keys'")
            return violations
        target = object_payload.get("type")
        allowed = declared_object.get("types") or []
        if target not in ENTITY_TYPES:
            violations.append(f"object entity type '{target}' is not declared")
        elif allowed and target not in allowed:
            violations.append(
                f"predicate '{predicate}' points at {', '.join(allowed)}, not '{target}'")
        keys = object_payload.get("keys")
        if not isinstance(keys, dict) or not keys:
            violations.append("an entity_ref payload must carry a non-empty structured "
                              "'keys' object - a concatenated string is refused by "
                              "design §3")
        else:
            expected = ENTITY_TYPES.get(target, {}).get("keys") or []
            missing = [k for k in expected if not str(keys.get(k) or "").strip()]
            if missing:
                violations.append(
                    f"object identity for '{target}' is missing {', '.join(missing)}")

        qualifiers = object_payload.get("qualifiers") or {}
        required = sig.get("qualifiers") or []
        if required:
            if not isinstance(qualifiers, dict):
                violations.append("'qualifiers' must be an object")
            else:
                absent = [q for q in required
                          if qualifiers.get(q) is None or str(qualifiers.get(q)).strip() == ""]
                if absent:
                    violations.append(
                        f"predicate '{predicate}' declares qualifier(s) "
                        f"{', '.join(required)}; missing or blank: {', '.join(absent)}")
                extra = [q for q in qualifiers if q not in required]
                if extra:
                    violations.append(
                        f"predicate '{predicate}' declares qualifiers "
                        f"{', '.join(required)}; undeclared: {', '.join(sorted(extra))}")
        elif qualifiers:
            violations.append(f"predicate '{predicate}' declares no qualifiers but "
                              f"{sorted(qualifiers)} were supplied")

    return violations


def check_subject_keys(subject_type, subject_keys):
    """Violations for a SUBJECT identity. Structured, complete, non-blank.

    Design §3's `subject` row records the incident this is built from: a concatenated
    key collapsed `a_b` -> `a` when one piece was blank, and 170,000 production rows
    followed. So the check is two-sided - the shape must be a mapping (never a string),
    AND every declared key part must actually carry a value.
    """
    violations = []
    if subject_type not in ENTITY_TYPES:
        return [f"subject type '{subject_type}' is not a declared entity type"]
    if not isinstance(subject_keys, dict) or not subject_keys:
        return ["subject_keys must be a non-empty structured object; a concatenated "
                "string is refused by design §3"]
    expected = ENTITY_TYPES[subject_type]["keys"]
    for part in expected:
        if str(subject_keys.get(part) or "").strip() == "":
            violations.append(f"subject identity for '{subject_type}' has no value for "
                              f"key part '{part}'")
    extra = [k for k in subject_keys if k not in expected]
    if extra:
        violations.append(f"subject identity for '{subject_type}' carries undeclared key "
                          f"part(s) {', '.join(sorted(extra))}")
    return violations


# ===========================================================================
# ROOT-KEY ROLLUP (ruling R-2026-08-15-O)
# ===========================================================================

def rollup_subject_types(root_type: str) -> tuple:
    """`root_type` plus every type that DECLARES it rolls up into it. Sorted, stable.

    🔴 THIS IS WHAT A WAFER-SCOPE READ JOINS ON, instead of `subject_type = 'Wafer'`.
    「What happened to this wafer」 has to include what happened to its bonding legs; a
    query pinned to one type answers a narrower question than the one the screen is asking
    and reports the difference as an absence.

    ⚠️ NOT every reader should call this. A registration existence check, a per-type
    census, a `GROUP BY subject_type` - those are legitimately type-specific and widening
    them would be a different defect. The test is whether the caller is asking about a
    SUBJECT (roll up) or about a TYPE (do not).
    """
    types = {root_type}
    types.update(name for name, entry in ENTITY_TYPES.items()
                 if entry.get("rolls_up_to") == root_type)
    return tuple(sorted(types))


def root_key(subject_type: str):
    """The key part a derived type shares with its root, or `None` for a root type."""
    return (ENTITY_TYPES.get(subject_type) or {}).get("root_key")


def check_entity_type_declaration():
    """Violations of the rollup declaration's own rules. Pure; a test is the enforcer.

    The same shape as `check_walk_declaration` and for the same reason: a rollup that can
    only ever be correct by accident is the decoy declaration again. A `rolls_up_to`
    naming a type that does not exist, or a `root_key` that is not actually a key part of
    BOTH types, would produce a query that joins on a jsonb field one side never carries -
    and that query returns zero extra rows rather than an error, which is indistinguishable
    from the bug this declaration exists to fix.
    """
    violations = []
    for name, entry in ENTITY_TYPES.items():
        root = entry.get("rolls_up_to")
        key = entry.get("root_key")
        if root is None and key is None:
            continue
        if root is None or key is None:
            violations.append(
                f"entity type '{name}' declares only one of rolls_up_to/root_key "
                f"({root!r}/{key!r}); a rollup needs both - the type to fold into and the "
                f"key to fold on")
            continue
        if root not in ENTITY_TYPES:
            violations.append(
                f"entity type '{name}' rolls up to '{root}', which is not a declared "
                f"entity type")
            continue
        if root == name:
            violations.append(f"entity type '{name}' rolls up to itself")
            continue
        if key not in (entry.get("keys") or []):
            violations.append(
                f"entity type '{name}' declares root_key '{key}', which is not one of its "
                f"own key parts ({', '.join(entry.get('keys') or [])}) - a read would join "
                f"on a field its atoms do not carry and quietly return nothing")
        if key not in (ENTITY_TYPES[root].get("keys") or []):
            violations.append(
                f"entity type '{name}' declares root_key '{key}', which is not a key part "
                f"of its root '{root}' ({', '.join(ENTITY_TYPES[root].get('keys') or [])})")
        if ENTITY_TYPES[root].get("rolls_up_to"):
            violations.append(
                f"entity type '{name}' rolls up to '{root}', which itself rolls up - "
                f"chained rollups are not implemented and a reader would silently stop "
                f"after one hop")
    return violations


def requires_register(entity_type: str) -> bool:
    """Issued entities need a `register` atom; composed ones are defined into existence."""
    return entity_type in ISSUED_TYPES
