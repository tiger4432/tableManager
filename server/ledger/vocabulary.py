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
    # One process run names SEVERAL things at once - a step, a machine, a recipe
    # revision, and the conditions it actually ran at. `entity_ref` points at exactly one
    # entity, so expressing this as entity_refs would need three atoms that are only
    # jointly true, and atomicity check ① ("is it true standing alone?") would fail for
    # each of them: "wafer W was processed on eqp B-3" standing alone does not say under
    # which recipe, and the pairing would have to be recovered from `occurred_at`
    # collisions. The run is ONE claim, so it is one atom.
    #
    # 🔴 `params_actual` IS WHAT MAKES «MEASURED BEATS SETPOINT» FREE
    # ----------------------------------------------------------------
    # An atom carrying `params_actual` is what the equipment log UTTERED, so it resolves
    # at class 2 (observation) by `ledger_trace.claim_class`'s default arm. An atom whose
    # parameters were filled in FROM THE RECIPE instead carries the payload flag
    # `inferred: true` (`DEFAULT_RESOLVER_CONFIG["inference_payload_flag"]`) and resolves
    # at class 3. No new ranking code exists anywhere: the setpoint fallback loses to the
    # measurement because the class boundary in `claim_rank_key` cannot be crossed by any
    # tiebreak below it - and it keeps losing even when the setpoint atom is NEWER and
    # comes from a higher-priority source, which is exactly the case the fixture builds.
    "processed_with": {
        "label_ko": "공정 처리",
        "status": "active", "since": 2, "layer": "ontology",
        "subject": ["Wafer"],
        # `required` is checked by `check_signature`; see the note there. Without it a
        # `value` object would be structurally unchecked, and a signature that checks
        # nothing is the decoy declaration ruling R-2026-08-13-D put an end to.
        "object": {"kind": "value",
                   "required": ["step", "step_family", "eqp", "recipe"]},
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
}

#: Predicates a translator may EMIT. `reserved` entries are declared so the vocabulary
#: is complete and so a future emitter does not re-mint the word under a second
#: spelling, but emitting one today is an undeclared-vocabulary refusal.
EMITTABLE = frozenset(name for name, sig in PREDICATES.items() if sig["status"] == "active")

#: The directions a traversable edge may be followed in (ruling R-2026-08-14-E). Closed,
#: because a direction nothing implements is a walk that silently goes the wrong way -
#: `ledger_trace` refuses a declaration it cannot execute BY NAME rather than falling back
#: to the direction it happens to have hard-coded.
WALK_DIRECTIONS = frozenset({"subject_to_object", "object_to_subject"})


def walk_predicates():
    """Every predicate the lineage walk may FETCH - traversable ones and annotations.

    🔴 This is what `ledger_trace.LINEAGE_PREDICATES` used to spell by hand. Derived, so
    admitting a word to the walk is a declaration change plus the vocabulary-pinning test,
    and EXCLUDING one (`observed`) is a thing the vocabulary can actually say.
    """
    return tuple(sorted(name for name, sig in PREDICATES.items()
                        if sig.get("traversable") is not None))


def traversable_predicates():
    """The predicates the walk RECURSES through. A subset of `walk_predicates()`."""
    return tuple(sorted(name for name, sig in PREDICATES.items()
                        if sig.get("traversable") is True))


def walk_direction(predicate):
    """Which way a traversable edge is followed, or `None` if it is not traversed."""
    return (PREDICATES.get(predicate) or {}).get("direction")


def check_walk_declaration():
    """Violations of the walk declaration's own rules. Pure; the test is the enforcer.

    Two directions of the same rule, because a declaration that can only ever be
    consistent-by-accident is the decoy again: a traversable edge with no direction would
    be walked whichever way the SQL happened to be written, and a direction on an edge
    nobody walks would teach a reader a constraint that binds nothing.
    """
    violations = []
    for name, sig in PREDICATES.items():
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
    return predicate in PREDICATES


def signature(predicate: str):
    return PREDICATES.get(predicate)


def check_signature(predicate, subject_type, object_kind, object_payload):
    """Return a list of signature violations. Empty list = the atom fits its declaration.

    Pure - takes no connection, keeps no state, and never logs. The gate owns counting
    and announcing; this owns only the judgement, so the judgement can be unit-tested
    without a database and reused by anything else that has to ask the same question.
    """
    violations = []

    if predicate in PROJECTION_ONLY_WORDS:
        return [f"'{predicate}' is a PROJECTION state word (design §4.2) and may never "
                f"be written to the ledger"]

    sig = PREDICATES.get(predicate)
    if sig is None:
        return [f"predicate '{predicate}' is not in the closed vocabulary"]
    if sig["status"] != "active":
        violations.append(f"predicate '{predicate}' is declared but its status is "
                          f"'{sig['status']}' - it may not be emitted yet")

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


def requires_register(entity_type: str) -> bool:
    """Issued entities need a `register` atom; composed ones are defined into existence."""
    return entity_type in ISSUED_TYPES
