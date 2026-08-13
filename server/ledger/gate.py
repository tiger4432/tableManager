"""The translation gate: it refuses at the door, and it COUNTS.

`server/chain_key_gate.py` is this project's worked example of a gate that names what it
refused, and this module is deliberately its sibling - same process-lifetime counters,
same escalating announce thresholds, same "the heartbeat note is `None` on a clean
worker" rule. What is different is the unit: `chain_key_gate` screens ROWS, this screens
MOLECULES, because `LEDGER_SLICE_1_BRIEF` §3-1 makes one source event the transaction
unit and a nine-atom molecule must never land half.

🔴 SILENT SKIPPING IS THE DEFECT, NOT THE MITIGATION
-----------------------------------------------------
`ROOT_DEFECTS`'s second root is "거절 못 함" - the system cannot say no, so it swallows
what it does not understand. A translator that drops an unrecognised `event_type` and
returns a tidy count is the same defect wearing a new coat. Every refusal here is
counted by `(source, reason)`, the counters survive for the life of the process, and the
digest goes into the worker's heartbeat note where `/health` can read it from another
process.

THE PREDICATE IS THE DESIGN'S FOUR ATOMICITY CHECKS
----------------------------------------------------
`CANONICAL_LEDGER_DESIGN.md` §3 ends with four questions and this module is where they
stop being prose:

  1. **Is it true alone?** -> `vocabulary.check_subject_keys` + `check_signature`. A
     structured, complete subject; an object that matches its declared shape; every
     declared qualifier present. `REFUSE_NOT_TRUE_ALONE`.
  2. **Does it land without halves?** -> `screen_molecule` is all-or-nothing. One bad
     atom refuses the WHOLE molecule, and the writer is handed molecules, never atoms,
     so there is no call path that can write a fragment. `REFUSE_ATOMICITY`.
  3. **Is it the utterance, not the conclusion?** -> every atom must name a `derivation`
     that the source's config DECLARED. A rule nobody declared cannot produce an atom,
     which is what stops a translator from quietly inferring. `REFUSE_UNDECLARED_DERIVATION`.
  4. **Can `raw_ref` re-utter it?** -> `envelope.check_envelope`. `REFUSE_NO_RAW_REF`.

There is a fifth question that is not one of the design's four, and it is here because
ruling R-2026-08-13-D put it here: **is this atom about something the source said it
would talk about?** The source's `subject_types` declares that extension, and an atom
outside it is `REFUSE_UNDECLARED_SUBJECT_TYPE`. It exists because the declaration used to
be read by nothing at all, so a translator could begin minting a new entity type and the
only trace would be a new value appearing in a column. Now it is a counted refusal with
a name, which is the difference between drift you find and drift that finds you.

WHY REFUSAL IS PER-MOLECULE AND NOT PER-ATOM
---------------------------------------------
Because a half-translated event is worse than an untranslated one. If `slot_map` #7 of a
split is malformed, keeping the other eight atoms produces a lineage that LOOKS complete
and is not - the exact failure mode "표식이 열쇠로" describes, where a partial record is
mistaken for a whole one. Refusing the molecule leaves a hole the lag report can see.
"""
from __future__ import annotations

import logging

from . import envelope, vocabulary

logger = logging.getLogger("Ledger.Gate")


# ---------------------------------------------------------------- refusal vocabulary
# Named, not numbered, for the reason `chain_key_gate.REFUSAL_UNKEYED_ROW` is: these
# strings appear in the operator's log and in `/health`, and a number there would need a
# lookup table that nobody keeps current.
REFUSE_UNDECLARED_SOURCE = "undeclared_source"
REFUSE_UNDECLARED_VOCABULARY = "undeclared_vocabulary"
REFUSE_NO_TIME_DECLARATION = "no_occurred_at_declaration"
REFUSE_MISSING_OCCURRED_AT = "missing_occurred_at"
REFUSE_NO_IDENTITY = "no_identity"
REFUSE_NOT_TRUE_ALONE = "not_true_alone"
REFUSE_ATOMICITY = "atomicity_violation"
REFUSE_UNDECLARED_DERIVATION = "undeclared_derivation"
REFUSE_NO_RAW_REF = "no_raw_ref"
REFUSE_PAYLOAD_NOT_PRESERVABLE = "payload_not_preservable"
#: A source row that names BOTH sides of a pair it is only allowed to name one of. Its
#: own reason rather than `no_identity`, because the identity is not missing - there are
#: two of them and nothing in the row says which one this event is.
REFUSE_AMBIGUOUS_PAIR = "ambiguous_pair"
#: An atom about an entity type the SOURCE never declared it speaks about (ruling
#: R-2026-08-13-D). Its own reason rather than `not_true_alone`, because the atom may be
#: perfectly true - the objection is that a translator started uttering a type nobody
#: reviewed, and that drift is only visible if it has a name of its own to be counted
#: under.
REFUSE_UNDECLARED_SUBJECT_TYPE = "undeclared_subject_type"

#: Every reason this gate can give. A test asserts the set is closed, for the same
#: reason the predicate vocabulary is closed: a reason invented at a call site is a
#: reason nobody can chart.
REFUSAL_REASONS = frozenset({
    REFUSE_UNDECLARED_SOURCE, REFUSE_UNDECLARED_VOCABULARY, REFUSE_NO_TIME_DECLARATION,
    REFUSE_MISSING_OCCURRED_AT, REFUSE_NO_IDENTITY, REFUSE_NOT_TRUE_ALONE,
    REFUSE_ATOMICITY, REFUSE_UNDECLARED_DERIVATION, REFUSE_NO_RAW_REF,
    REFUSE_PAYLOAD_NOT_PRESERVABLE, REFUSE_AMBIGUOUS_PAIR,
    REFUSE_UNDECLARED_SUBJECT_TYPE,
})

# Detail is capped, counts never are - every detail string here derives from SOURCE
# data, so a malformed feed must not be able to grow the report without limit. Same
# discipline as `chain_key_gate.MAX_REFUSAL_ROWS`.
MAX_REFUSAL_SAMPLES = 20
_ANNOUNCE_AT = frozenset([1, 10, 100, 1000, 10000, 100000, 1000000])
_NOTE_TOP_N = 5

# (source, reason) -> molecules refused, for the life of this process.
_refusals: dict = {}
# source -> atoms that were BUILT and then thrown away with their molecule.
# 🔴 This is not "how much was lost". A molecule refused BEFORE any atom exists - an
# undeclared event_type, an unparseable time, an ambiguous pair - contributes ZERO here
# and still loses everything that row would have produced. Reporting 0 as if it were the
# loss is how an instrument lies while telling the truth, so the SOURCE ROWS refused are
# counted separately below and both numbers appear in the note. Neither one alone is
# the answer to "how much am I losing", and pretending otherwise was this module's own
# first defect (caught on the first real run: 1 refused row, 26 atoms never written,
# `atoms_lost=0`).
_atoms_lost: dict = {}
# source -> SOURCE ROWS that produced nothing because their molecule was refused.
_rows_refused: dict = {}
# source -> molecules that translated but whose SOURCE was incomplete. NOT a refusal -
# the atoms are true - but it is the number that explains a chain with a hole in it, so
# it rides in the same heartbeat.
_incomplete: dict = {}
_samples: list = []


def refusals() -> dict:
    """`{(source, reason): molecules}` so far in this process. A copy."""
    return dict(_refusals)


def atoms_lost() -> dict:
    """`{source: atoms}` that were built and then thrown away with their molecule."""
    return dict(_atoms_lost)


def rows_refused() -> dict:
    """`{source: rows}` whose molecule was refused, whether or not atoms were built."""
    return dict(_rows_refused)


def incomplete_molecules() -> dict:
    """`{source: molecules}` translated from an incomplete source event."""
    return dict(_incomplete)


def samples() -> list:
    """Up to `MAX_REFUSAL_SAMPLES` named refusals, for the report and for `/health`."""
    return list(_samples)


def reset_counters():
    """Drop the process counters. For tests only - nothing in production calls this."""
    _refusals.clear()
    _atoms_lost.clear()
    _rows_refused.clear()
    _incomplete.clear()
    del _samples[:]


def note():
    """Heartbeat digest, or `None` while nothing is being refused.

    `None` on a clean translator is load-bearing in the same way it is for
    `chain_key_gate.note()`: a healthy deployment's heartbeat stays quiet, so a line
    appearing in it is itself the signal.
    """
    if not _refusals and not _incomplete:
        return None
    parts = []
    if _refusals:
        top = sorted(_refusals.items(), key=lambda kv: -kv[1])[:_NOTE_TOP_N]
        detail = ", ".join(f"{src}:{reason}={n}" for (src, reason), n in top)
        if len(_refusals) > len(top):
            detail += f" (+{len(_refusals) - len(top)} more)"
        parts.append(f"ledger gate refusals: molecules={sum(_refusals.values())} "
                     f"source_rows={sum(_rows_refused.values())} "
                     f"built_atoms_discarded={sum(_atoms_lost.values())} | {detail}")
    if _incomplete:
        parts.append("incomplete source molecules: " + ", ".join(
            f"{src}={n}" for src, n in sorted(_incomplete.items())))
    return " || ".join(parts)


def record_incomplete(source: str, count: int = 1):
    """A molecule whose source event arrived without all of its rows.

    Deliberately NOT a refusal. The rows that DID arrive utter true claims and dropping
    them would destroy evidence; what the operator needs is to know the chain built from
    them has a hole. `lot_event`'s browser-edited pair is exactly this case: someone
    retyped `child_lot`, so the two rows of one merge no longer name the same pair, and
    both halves are now separately true and separately incomplete.
    """
    _incomplete[source] = _incomplete.get(source, 0) + int(count)


def _record(source: str, reason: str, atoms: int, detail: str, rows: int = 1):
    key = (source, reason)
    before = _refusals.get(key, 0)
    total = before + 1
    _refusals[key] = total
    _atoms_lost[source] = _atoms_lost.get(source, 0) + int(atoms)
    _rows_refused[source] = _rows_refused.get(source, 0) + int(rows)
    if len(_samples) < MAX_REFUSAL_SAMPLES:
        _samples.append({"source": source, "reason": reason, "atoms": int(atoms),
                         "rows": int(rows), "detail": detail})
    # Announce on the 1st, 10th, 100th ... occurrence so a fixed deployment and a
    # broken one do not produce identical logs.
    if total in _ANNOUNCE_AT:
        logger.warning(
            "[LedgerGate] source=%s REFUSED a source event at the door | reason=%s | "
            "%d source row(s) produced nothing; %d atom(s) had already been built and "
            "were discarded so the molecule could not land half | %s | refused so far "
            "in this process for this reason: %d",
            source, reason, rows, atoms, detail, total)
    else:
        logger.info(
            "[LedgerGate] source=%s refused (%s), %d row(s): %s | total for this "
            "reason: %d", source, reason, rows, detail, total)


def refuse(source: str, reason: str, detail: str, atoms: int = 0, rows: int = 1):
    """Refuse something that never became atoms at all - an undeclared `event_type`, a
    source with no declared time column, a molecule with no resolvable subject.

    Separate from `screen_molecule` because these refusals happen BEFORE any atom
    exists, and forcing the caller to build a fake atom just to be refused would be a
    worse contract than two entry points.
    """
    if reason not in REFUSAL_REASONS:
        # A reason nobody declared cannot be charted, and the gate refusing to invent
        # one is the same rule the gate applies to predicates.
        raise ValueError(f"'{reason}' is not a declared refusal reason "
                         f"({sorted(REFUSAL_REASONS)})")
    _record(source, reason, atoms, detail, rows=rows)


def screen_molecule(source: str, atoms, declared_derivations, declared_subject_types,
                    molecule_ref=None, source_rows: int = 1):
    """Judge ONE source event's atoms. Returns `(kept, report)`; `kept` is all or none.

    `declared_derivations` is the set of derivation names the SOURCE's config declared.
    An atom whose `derivation` is outside it is refused even if it is otherwise perfect -
    that is atomicity check ③ in mechanical form. Passing an empty set therefore refuses
    everything, which is the correct direction: a source that declared no rules must not
    be able to produce atoms.

    `declared_subject_types` is the same idea one axis over - the entity types the source
    declared its translator may speak ABOUT (ruling R-2026-08-13-D). It is REQUIRED rather
    than defaulted for the reason the ruling exists: a default would let a caller keep the
    old behaviour by saying nothing, and a check that can be silently skipped is the decoy
    field again in a new place. Empty refuses everything, deliberately.
    """
    atoms = list(atoms or ())
    report = {
        "source": source,
        "molecule_ref": molecule_ref,
        "atoms": len(atoms),
        "refused": False,
        "reason": None,
        "violations": [],
    }

    if not atoms:
        # Not an error. A `track_in` for a lot whose wafer column is entirely blank
        # legitimately produces nothing, and counting that as a refusal would make the
        # refusal counter mean two different things.
        return [], report

    declared = frozenset(declared_derivations or ())
    allowed_subjects = frozenset(declared_subject_types or ())
    for index, atom in enumerate(atoms):
        where = f"atom[{index}] {atom.describe()}"

        if atom.subject_type not in allowed_subjects:
            # Checked BEFORE the identity and signature checks so the reason names what
            # actually happened. `check_subject_keys` would also refuse an unknown type,
            # but under `no_identity` - and "this lot has no identity" is a very
            # different report from "this translator has started talking about
            # equipment", which is the drift this refusal exists to surface.
            report.update(refused=True, reason=REFUSE_UNDECLARED_SUBJECT_TYPE)
            report["violations"].append(
                f"{where}: subject type {atom.subject_type!r} is outside the types "
                f"source '{source}' declared it speaks about (declared: "
                f"{', '.join(sorted(allowed_subjects)) or 'none'}). The atom may well be "
                f"true; what is missing is the vocabulary review that adding a type to "
                f"`subject_types` is - declare it there and this atom lands.")
            break

        if atom.derivation not in declared:
            report.update(refused=True, reason=REFUSE_UNDECLARED_DERIVATION)
            report["violations"].append(
                f"{where}: derivation {atom.derivation!r} was not declared for source "
                f"'{source}' (declared: {', '.join(sorted(declared)) or 'none'}) - "
                f"atomicity check 3: an atom may only record a rule somebody declared")
            break

        subject_violations = vocabulary.check_subject_keys(atom.subject_type,
                                                          atom.subject_keys)
        if subject_violations:
            report.update(refused=True, reason=REFUSE_NO_IDENTITY)
            report["violations"].extend(f"{where}: {v}" for v in subject_violations)
            break

        signature_violations = vocabulary.check_signature(
            atom.predicate, atom.subject_type, atom.object_kind, atom.object_payload)
        if signature_violations:
            reason = (REFUSE_UNDECLARED_VOCABULARY
                      if not vocabulary.is_declared(atom.predicate)
                      else REFUSE_NOT_TRUE_ALONE)
            report.update(refused=True, reason=reason)
            report["violations"].extend(f"{where}: {v}" for v in signature_violations)
            break

        envelope_violations = envelope.check_envelope(atom)
        if envelope_violations:
            reason = REFUSE_NOT_TRUE_ALONE
            for violation in envelope_violations:
                if "raw_ref" in violation:
                    reason = REFUSE_NO_RAW_REF
                elif "occurred_at" in violation:
                    reason = REFUSE_MISSING_OCCURRED_AT
                elif "NaN" in violation or "no JSON spelling" in violation \
                        or "non-string key" in violation:
                    reason = REFUSE_PAYLOAD_NOT_PRESERVABLE
                break
            report.update(refused=True, reason=reason)
            report["violations"].extend(f"{where}: {v}" for v in envelope_violations)
            break

        if molecule_ref is not None and atom.molecule_ref != molecule_ref:
            # An atom that belongs to a different molecule has been mixed into this
            # transaction unit. Nothing downstream would notice, and the all-or-nothing
            # guarantee would already be broken by the time it did.
            report.update(refused=True, reason=REFUSE_ATOMICITY)
            report["violations"].append(
                f"{where}: molecule_ref {atom.molecule_ref!r} does not belong to the "
                f"transaction unit {molecule_ref!r}")
            break

    if report["refused"]:
        _record(source, report["reason"], len(atoms),
                f"molecule={molecule_ref} :: " + " ; ".join(report["violations"][:3]),
                rows=source_rows)
        return [], report

    return atoms, report
