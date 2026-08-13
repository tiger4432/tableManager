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
"""
from __future__ import annotations

#: Object kinds, exactly as pinned for slice 1. `None` additionally means ∅ and is
#: legal only for a predicate whose signature declares `object` as `None`.
OBJECT_KINDS = frozenset({"value", "entity_ref", "event_ref"})


#: Entity types (§4.2). `register` is required for ISSUED types and forbidden for
#: COMPOSED ones - `Die` exists by construction (Wafer x product grid) and registering
#: it would mean 160M register atoms for no gain (§5 rule 3).
ENTITY_TYPES = {
    "Lot":       {"class": "issued",   "keys": ["lot"],       "semi_ref": "E90 substrate"},
    "Wafer":     {"class": "issued",   "keys": ["wafer"],     "semi_ref": "E90 substrate"},
    "Product":   {"class": "issued",   "keys": ["product"],   "semi_ref": None},
    "Equipment": {"class": "issued",   "keys": ["equipment"], "semi_ref": "E10"},
    "Die":       {"class": "composed", "keys": ["wafer", "x", "y"], "semi_ref": "E142 location"},
}

ISSUED_TYPES = frozenset(k for k, v in ENTITY_TYPES.items() if v["class"] == "issued")


#: The seven. `status`/`since`/`superseded_by` are the §4.3 signature fields; they are
#: carried even though nothing is deprecated yet, because the day something is, the
#: field has to already exist or the deprecation has nowhere to be written.
PREDICATES = {
    # ---------------------------------------------------------------- §4.1 canonical
    "register": {
        "status": "active", "since": 1, "layer": "canonical",
        "subject": ["Lot", "Wafer", "Product", "Equipment"],
        "object": None,                       # ∅ - see module docstring
        "qualifiers": [],
        "unit": None, "semi_ref": "local", "superseded_by": None,
    },
    "pin": {
        "status": "active", "since": 1, "layer": "canonical",
        "subject": ["Lot", "Wafer", "Product", "Equipment", "Die"],
        "object": {"kind": "event_ref"},
        "qualifiers": [],
        "unit": None, "semi_ref": "local", "superseded_by": None,
    },
    "same_as": {
        "status": "reserved", "since": 1, "layer": "canonical",
        "subject": ["Lot", "Wafer", "Product", "Equipment", "Die"],
        "object": {"kind": "entity_ref", "types": ["Lot", "Wafer", "Product", "Equipment", "Die"]},
        "qualifiers": [],
        "unit": None, "semi_ref": "local", "superseded_by": None,
    },
    # ---------------------------------------------------------------- §4.2 ontology
    "derived_from": {
        "status": "active", "since": 1, "layer": "ontology",
        "subject": ["Lot"],
        "object": {"kind": "entity_ref", "types": ["Lot"]},
        "qualifiers": [],
        "unit": None, "semi_ref": "E90 genealogy", "superseded_by": None,
    },
    "slot_map": {
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
    },
    "has_wafer": {
        "status": "active", "since": 1, "layer": "ontology",
        "subject": ["Lot"],
        "object": {"kind": "entity_ref", "types": ["Wafer"]},
        "qualifiers": ["slot"],
        "unit": None, "semi_ref": "E90", "superseded_by": None,
    },
    "frame_confirmed": {
        "status": "reserved", "since": 1, "layer": "ontology",
        "subject": ["Wafer"],
        "object": {"kind": "value"},
        "qualifiers": [],
        "unit": None, "semi_ref": "E142 coordinate system", "superseded_by": None,
    },
}

#: Predicates a translator may EMIT. `reserved` entries are declared so the vocabulary
#: is complete and so a future emitter does not re-mint the word under a second
#: spelling, but emitting one today is an undeclared-vocabulary refusal.
EMITTABLE = frozenset(name for name, sig in PREDICATES.items() if sig["status"] == "active")

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
