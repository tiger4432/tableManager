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

  1. **Is it true alone?** -> the DECLARATION answers this now. It used to be
     `vocabulary.check_subject_keys` + `check_signature` against `ledger/vocabulary.py`;
     that file retired 2026-08-27 and the v5 emit path assembles an atom from a compiled
     Role map instead, so a shape the declaration does not describe never reaches here.
     `REFUSE_NOT_TRUE_ALONE` remains for the checks below that still produce it.
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

🔴 AND IT IS ENFORCED HERE, NOT BY EVERY AUTHOR REMEMBERING IT (ruling R-2026-08-13-H)
---------------------------------------------------------------------------------------
The standing principle: **if `refuse` fires on ANY fragment of a molecule, that molecule
contributes zero atoms.** Per-fragment survival is what `incomplete` is for - a true but
incomplete utterance - and collapsing the two gives a ledger where something was refused
and half of it is stored.

A translator therefore builds its atoms inside `building_molecule`, and every `refuse`
underneath it RAISES `MoleculeRefused` rather than returning a value somebody has to
check. It used to return one; one caller merged it with `... or []` and three atoms of a
refused molecule landed.

🔴 AND THE SCOPE IS OPENED BY THE SHARED DRIVER, NOT BY EACH TRANSLATOR (R-H-bis 3)
------------------------------------------------------------------------------------
"The next translator inherits this only if it opens the scope" was the remaining hole:
a discipline a second author has to DISCOVER is oral tradition, not structure. So the
loop that walks molecules (`backfill.run`) holds the `with`, every translator it drives
is born inside it, and `_build`'s `molecule_is_open()` assertion is kept as the second
net rather than the first. `screen_molecule` refuses through `refuse` for the same
reason (R-H-bis 1): one grammar, so a future caller cannot pick the wrong one.
"""
from __future__ import annotations

import contextlib
import logging
import threading

from . import envelope

logger = logging.getLogger("Ledger.Gate")


# ------------------------------------------------------- the refusal that cannot be lost
class MoleculeRefused(Exception):
    """`refuse` fired while a molecule was being built, so that molecule is over.

    🔴 WHY AN EXCEPTION AND NOT A RETURN VALUE - ruling R-2026-08-13-H.
    `lot_event_translator` used to signal a fragment-level refusal by returning `None`
    from the helper that built the fragment, and one call site merged the result with
    `... or []`. Measured on a real backfill: the gate counted `atomicity_violation`, the
    log said "1 source row(s) produced nothing", and THREE atoms of that molecule landed
    anyway - a ledger where something was refused and half of it is stored, which is the
    exact shape §10-bis disqualifies the current system for. The cursor then read
    `molecules_refused=0` beside a breakdown summing to 1 (`refusals_unaccounted = -1`).

    Returning `[]` instead of `None` would have fixed that one line and left the hole:
    the next helper written the same way is re-broken by the next convenience. An
    exception is the only shape no merge expression can swallow, so the signal survives
    `or []`, `or {}`, a bare `extend`, and an ignored return value alike.
    """

    def __init__(self, source: str, reason: str, detail: str):
        super().__init__(f"{source}: {reason}: {detail}")
        self.source = source
        self.reason = reason
        self.detail = detail


#: Per-thread depth of open molecules. Thread-local rather than a module global because
#: the refusal is about ONE execution's molecule, while the counters below are process
#: aggregates on purpose - two translators in two threads must share the counts and must
#: NOT share each other's abort.
_open = threading.local()


@contextlib.contextmanager
def building_molecule(source: str):
    """While this is open, ANY `refuse` for any source aborts by raising.

    The caller does not have to remember to use a special refusal function, and a helper
    added later does not have to know this rule exists - it calls `gate.refuse` like
    every other refusal site and its molecule stops. That is the point: the standing
    principle (a refusal on any fragment means the molecule contributes zero atoms) is
    enforced by the gate rather than by every author remembering it.

    🔴 WHO OPENS IT: the SHARED DRIVER that walks molecules, not the translator (ruling
    R-2026-08-13-H-bis 3). A translator that opened its own scope passed the discipline
    on by word of mouth - the second translator inherits it only if its author reads the
    first one and notices. With `backfill.run` holding the `with`, a translator is
    structurally born inside the scope and cannot be written outside it; `_build`'s
    `molecule_is_open()` assertion stays as the second net for a driver that forgets.

    `screen_molecule` refuses through `refuse` like everything else (ruling R-H-bis 1),
    so a molecule the GATE rejects unwinds here too - which is why the driver screens
    inside this scope rather than after it.
    """
    _open.depth = getattr(_open, "depth", 0) + 1
    try:
        yield
    finally:
        _open.depth -= 1


def molecule_is_open() -> bool:
    """Whether a refusal on this thread would abort a molecule right now.

    A translator's atom-building body asserts this rather than assuming it: outside the
    scope every `refuse` would only COUNT, execution would carry on past the check that
    was meant to stop it, and the result would be the half-landing again.
    """
    return getattr(_open, "depth", 0) > 0


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


#: Serialises `captured()`. The counters are PROCESS aggregates on purpose (see `_open`'s
#: note above), so two overlapping captures would each hand back the other's refusals.
_capture_lock = threading.Lock()


@contextlib.contextmanager
def captured():
    """Run something and collect ONLY its refusals, leaving the process counters intact.

    🔴 WHY THIS EXISTS: the admin dry run drives the REAL translators through the REAL
    gate (ruling R-2026-08-15-M ⑥ -「가짜 미리보기는 조용한 거짓말」), and the gate's
    counters are what `/health` and the heartbeat report. Without this, an operator
    previewing a declaration would raise the live refusal totals of a source that refused
    nothing, and「거절이 쌓이나」would answer yes because somebody looked.

    Yields a dict that is filled in on exit with the same shapes the module-level readers
    return, so a caller reports a dry run's refusals with the code that reports a run's.
    """
    with _capture_lock:
        saved = (dict(_refusals), dict(_atoms_lost), dict(_rows_refused),
                 dict(_incomplete), list(_samples))
        reset_counters()
        handle = {}
        try:
            yield handle
        finally:
            # Filled BEFORE the restore and inside `finally`, so a refusal that arrived
            # as an exception is still reported rather than lost with the unwind.
            handle["refusals"] = dict(_refusals)
            handle["atoms_lost"] = dict(_atoms_lost)
            handle["rows_refused"] = dict(_rows_refused)
            handle["incomplete"] = dict(_incomplete)
            handle["samples"] = list(_samples)
            reset_counters()
            _refusals.update(saved[0])
            _atoms_lost.update(saved[1])
            _rows_refused.update(saved[2])
            _incomplete.update(saved[3])
            _samples.extend(saved[4])


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

    🔴 Inside `building_molecule` this RAISES `MoleculeRefused` after counting (ruling
    R-2026-08-13-H). Counting first is deliberate - the refusal is a fact whether or not
    anybody catches the exception - and raising second is what stops the caller from
    counting a refusal and then writing the molecule anyway. Outside a molecule scope it
    only counts, which is what `backfill.run` needs when it refuses a whole SOURCE: there
    is no molecule in flight to abort.
    """
    if reason not in REFUSAL_REASONS:
        # A reason nobody declared cannot be charted, and the gate refusing to invent
        # one is the same rule the gate applies to predicates.
        raise ValueError(f"'{reason}' is not a declared refusal reason "
                         f"({sorted(REFUSAL_REASONS)})")
    _record(source, reason, atoms, detail, rows=rows)
    if molecule_is_open():
        raise MoleculeRefused(source, reason, detail)


def screen_molecule(source: str, atoms, declared_derivations, declared_subject_types,
                    molecule_ref=None, source_rows: int = 1):
    """Judge ONE source event's atoms. Returns `(kept, report)`, or RAISES on a refusal.

    🔴 THE REFUSAL LEAVES AS `MoleculeRefused`, NOT AS `[]` (ruling R-H-bis 1). Called
    inside `building_molecule` - which is where the driver calls it - a refused molecule
    unwinds; the returned `(kept, report)` pair is therefore only ever the ACCEPTING
    answer, and `kept` is every atom that went in. Outside a scope it degrades to the old
    `([], report)` with `report["refused"]` set, because `refuse` only counts there; that
    is the double net, not a second contract to program against.

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
        # Not an error, and THE ONLY `[]` this function still returns on its own account.
        # A `track_in` for a lot whose wafer column is entirely blank legitimately
        # produces nothing, and counting that as a refusal would make the refusal counter
        # mean two different things. It stays a return rather than joining the exception
        # grammar for exactly that reason: nothing was refused, so there is nothing to
        # abort. Since ruling R-H-bis the two are no longer spelled alike - a refusal
        # leaves through `MoleculeRefused`, silence leaves through here.
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

        # 🔴 THE v1 VOCABULARY CHECKS LEFT HERE 2026-08-27, BY OWNER'S RULING:
        #「그냥 걷어냅니다. 쓰기가 깨지면 그때 선언 위에서」. They were
        # `vocabulary.check_subject_keys` (-> REFUSE_NO_IDENTITY) and
        # `vocabulary.check_signature` (-> REFUSE_UNDECLARED_VOCABULARY / NOT_TRUE_ALONE),
        # and both judged an atom against `server/ledger/vocabulary.py` - the file this
        # retirement deletes. What they enforced is now the DECLARATION's business: the v5
        # emit path builds an atom from a compiled Role map, so an atom whose shape the
        # declaration does not describe cannot be assembled to arrive here.
        #
        # ⚠️ SAID PLAINLY, because it is a real change and not a tidy-up: an atom
        # handed to this gate by any OTHER path is no longer signature-checked here. The two
        # reason codes stay in `REASONS` - `refuse()` is called with them from elsewhere -
        # but nothing in this function produces them any more.

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
        # 🔴 ONE SIGNALLING GRAMMAR, NOT TWO (ruling R-2026-08-13-H-bis 1).
        # This used to call `_record` and hand back `[]`. That is the shape R-H executed
        # one module over: a refusal expressed as an EMPTY COLLECTION is swallowed by
        # `or []`, by a bare `extend`, and by an ignored return - and it is spelled
        # identically to the "this molecule legitimately had nothing to say" return
        # twenty lines up, so no caller can tell the two apart by looking. Going out
        # through `refuse` counts exactly as before and then RAISES `MoleculeRefused`
        # while a molecule scope is open, which is the one shape no merge expression can
        # absorb. Outside a scope `refuse` only counts, so the fall-through below is the
        # double net: a caller that never opened a scope still gets `[]` and a report,
        # never a silent pass.
        refuse(source, report["reason"],
               f"molecule={molecule_ref} :: " + " ; ".join(report["violations"][:3]),
               atoms=len(atoms), rows=source_rows)
        return [], report

    return atoms, report


def screen_compiled_molecule(source: str, atoms, declared_derivations,
                             declared_subject_types, molecule_ref=None,
                             source_rows: int = 1):
    """Gate a Stage-4-compiled molecule without reintroducing legacy vocabulary.

    Pack/Vocabulary/Entity semantics were already checked while producing the closed
    LedgerFrame.  This existing gate module still owns the live atomicity boundary:
    source/derivation scope, envelope preservation, molecule membership, refusal
    accounting, and the unwind signal are applied here.  Accepting a raw mapper output
    is not supported; the Stage 6 runtime calls this only after the Pack compiler and
    ``atoms_from_ledger_frame`` validator.
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
        return [], report

    declared = frozenset(declared_derivations or ())
    allowed_subjects = frozenset(declared_subject_types or ())
    for index, atom in enumerate(atoms):
        where = f"atom[{index}] {atom.describe()}"
        if atom.subject_type not in allowed_subjects:
            report.update(refused=True, reason=REFUSE_UNDECLARED_SUBJECT_TYPE)
            report["violations"].append(
                f"{where}: subject type {atom.subject_type!r} is outside the "
                "compiled source contract")
            break
        if atom.derivation not in declared:
            report.update(refused=True, reason=REFUSE_UNDECLARED_DERIVATION)
            report["violations"].append(
                f"{where}: derivation {atom.derivation!r} is outside the compiled "
                "source contract")
            break
        envelope_violations = envelope.check_envelope(atom)
        if envelope_violations:
            reason = REFUSE_NOT_TRUE_ALONE
            for violation in envelope_violations:
                if "raw_ref" in violation:
                    reason = REFUSE_NO_RAW_REF
                elif "occurred_at" in violation:
                    reason = REFUSE_MISSING_OCCURRED_AT
                elif ("NaN" in violation or "no JSON spelling" in violation
                      or "non-string key" in violation):
                    reason = REFUSE_PAYLOAD_NOT_PRESERVABLE
                break
            report.update(refused=True, reason=reason)
            report["violations"].extend(
                f"{where}: {violation}" for violation in envelope_violations)
            break
        if molecule_ref is not None and atom.molecule_ref != molecule_ref:
            report.update(refused=True, reason=REFUSE_ATOMICITY)
            report["violations"].append(
                f"{where}: molecule_ref {atom.molecule_ref!r} does not belong to "
                f"transaction unit {molecule_ref!r}")
            break

    if report["refused"]:
        refuse(source, report["reason"],
               f"molecule={molecule_ref} :: " +
               " ; ".join(report["violations"][:3]),
               atoms=len(atoms), rows=source_rows)
        return [], report
    return atoms, report
